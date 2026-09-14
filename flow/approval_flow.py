"""环节三 审批流转（PRD 2.7.1 审批能力、7.2、7.3）。

职责：审批结论处理（通过 / 退回 / 驳回）、审批节点流转与审批任务生成、单据状态流转与审批留痕。
本环节对应后端「审批流程模块」与「审核模块」（PRD 2.7.9），**是 approval_status 消息的出口**（PRD 20.3）。

边界与约定：
* 审批是否通过必须由有权限的人员人工确认，本环节只执行其结论，不代替审批人下结论（PRD 2.7.14）；
* 状态流转必须按 PRD 7.3 的表校验；下一节点与审批人由后端匹配审批流程后传入（PRD 7.2）；
* 审批结果须记录操作人、操作时间与审批意见（PRD 2.7.14），留痕只可追加（PRD 20.1 P7）。
"""

from datetime import datetime, timezone  # 任务处理时间与留痕时间（PRD 12.2：时间戳统一 UTC）

from agent.utils.message import MessagePublisher  # 实时消息推送（PRD 14.2）
from flow.audit_log_flow import AuditLogFlow  # 环节七 操作审计：本环节写审批操作留痕
from flow.status_transitions import ALLOWED_TRANSITIONS  # PRD 7.3 状态流转表（与环节一共用）
from schema.enums import (  # 审批实例状态、审批任务状态、单据状态
    ApprovalInstanceStatus, ApprovalTaskStatus, DocumentStatus,
)
from schema.messages import ApprovalStatusMessage, DocumentStatusMessage  # 状态变化消息（PRD 14.2）
from schema.tables_approval import (  # 审批实例、审批任务、审批节点定义、单据状态留痕
    ApprovalInstance, ApprovalTask, ApprovalWorkflowNode, DocumentStatusLog,
)
from schema.tables_document import FinancialDocument  # 被审批的单据

__all__ = ["ApprovalFlow"]


class ApprovalFlow:
    """环节三 审批流转（PRD 2.7.1 审批能力、7.3）。"""

    def __init__(self, publisher: MessagePublisher, audit_log: AuditLogFlow) -> None:
        """注入消息出口与审计环节。"""
        self.publisher = publisher  # approval_status 消息由本环节推送（PRD 20.3）
        self.audit_log = audit_log  # 审批操作留痕（PRD 2.7.9 日志模块）
        self.status_logs: list[DocumentStatusLog] = []  # 本环节产生的状态留痕

    def approve(self, document: FinancialDocument, instance: ApprovalInstance, task: ApprovalTask,
                next_node: ApprovalWorkflowNode | None,
                next_approver_id: int | None) -> tuple[ApprovalTask, ApprovalTask | None]:
        """通过当前审批节点：末节点通过则单据状态变为 approved，否则生成下一节点任务。

        依据 PRD 7.2 节点流转与 7.3 状态流转；下一节点与审批人由后端匹配审批流程后传入。
        返回 ``(已处理任务, 下一节点任务或 None)``。
        """
        # 步骤 1：置当前任务为已通过，并记录处理完成时间（PRD 2.7.12 审批任务状态）
        task.task_status = ApprovalTaskStatus.APPROVED
        task.processed_at = datetime.now(timezone.utc)
        # 步骤 2：写审批操作留痕——操作人、操作时间与审批意见（PRD 2.7.14）
        self._audit(task)
        # 步骤 3：审批人已介入，单据由 pending_review 流转到 reviewing（PRD 7.3「开始审批」）
        self._start_review(document, task)
        # 步骤 4：分支判断——是否还有下一审批节点（PRD 7.2 节点流转）
        if next_node is not None:  # 非末节点：流转到下一节点并生成新任务
            instance.current_node_id = next_node.id
            next_task = ApprovalTask(id=0, instance_id=instance.id, node_id=next_node.id,
                                     approver_id=next_approver_id,
                                     task_status=ApprovalTaskStatus.PENDING,
                                     created_at=task.processed_at)
            # 步骤 5a：推送新任务的审批状态变化消息（PRD 14.2）
            self._push_approval(document, instance, next_task)
            return task, next_task
        # 步骤 5b：末节点——实例结束（PRD 7.2 末节点通过后单据状态变为已通过）
        instance.instance_status = ApprovalInstanceStatus.APPROVED
        instance.finished_at = task.processed_at
        # 步骤 6b：单据流转 reviewing → approved（终态），并追加状态留痕（PRD 7.3）
        self._change_status(document, DocumentStatus.APPROVED, task.approver_id, task.review_comment)
        # 步骤 7b：推送审批状态变化消息（PRD 14.2）
        self._push_approval(document, instance, task)
        return task, None

    def return_back(self, document: FinancialDocument, instance: ApprovalInstance,
                    task: ApprovalTask) -> ApprovalTask:
        """退回单据：允许申请人修改后重新提交（PRD 7.2 退回重提、7.3）。"""
        # 步骤 1：统一走节点结论处理——任务置已退回、单据置 returned、实例置已退回
        return self._settle(document, instance, task, ApprovalTaskStatus.RETURNED,
                            DocumentStatus.RETURNED, ApprovalInstanceStatus.RETURNED)

    def reject(self, document: FinancialDocument, instance: ApprovalInstance,
               task: ApprovalTask) -> ApprovalTask:
        """驳回单据：单据状态变为 rejected 并进入终态（PRD 7.2、7.3）。"""
        # 步骤 1：统一走节点结论处理——任务置已驳回、单据置 rejected、实例置已驳回
        return self._settle(document, instance, task, ApprovalTaskStatus.REJECTED,
                            DocumentStatus.REJECTED, ApprovalInstanceStatus.REJECTED)

    def _settle(self, document: FinancialDocument, instance: ApprovalInstance, task: ApprovalTask,
                task_status: ApprovalTaskStatus, document_status: DocumentStatus,
                instance_status: ApprovalInstanceStatus) -> ApprovalTask:
        """节点结论处理：置任务与实例状态 → 流转单据状态 → 推送消息并留痕（PRD 7.2）。"""
        # 步骤 1：置任务状态与处理完成时间（PRD 2.7.12 审批任务状态）
        task.task_status = task_status
        task.processed_at = datetime.now(timezone.utc)
        # 步骤 2：写审批操作留痕（PRD 2.7.14）
        self._audit(task)
        # 步骤 3：审批人已介入，单据由 pending_review 流转到 reviewing（PRD 7.3「开始审批」）
        self._start_review(document, task)
        # 步骤 4：置实例状态并结束该实例（PRD 2.7.12 审批实例状态）
        instance.instance_status = instance_status
        instance.finished_at = task.processed_at
        # 步骤 5：单据流转到结论对应的目标状态（returned / rejected），追加留痕并推送（PRD 7.3）
        self._change_status(document, document_status, task.approver_id, task.review_comment)
        # 步骤 6：推送 approval_status 消息（PRD 14.2）
        self._push_approval(document, instance, task)
        # 步骤 7：返回已处理的任务
        return task

    def _start_review(self, document: FinancialDocument, task: ApprovalTask) -> None:
        """审批人介入即流转 pending_review → reviewing（PRD 7.3「开始审批」）。"""
        # 步骤 1：仅当单据仍停在 pending_review 时才需要这一步；已进入 reviewing 则跳过
        if document.document_status is DocumentStatus.PENDING_REVIEW:
            # 步骤 2：流转到 reviewing，并追加状态留痕、推送 document_status（PRD 7.3）
            self._change_status(document, DocumentStatus.REVIEWING, task.approver_id, "开始审批")

    def _push_approval(self, document: FinancialDocument, instance: ApprovalInstance,
                       task: ApprovalTask) -> None:
        """推送审批状态变化消息（PRD 14.2 approval_status）。"""
        # 步骤 1：按 PRD 14.2 的字段构造并推送——单据、实例、当前节点与该节点任务状态
        self.publisher.publish("approval_status",
                               ApprovalStatusMessage(document.id, instance.id, task.node_id,
                                                     task.task_status))

    def _audit(self, task: ApprovalTask) -> None:
        """记录审批操作留痕：操作人、操作时间与审批意见（PRD 2.7.14）。"""
        # 步骤 1：以审批任务为资源写留痕，操作人取任务上的审批人，变更内容为任务状态与审批意见
        self.audit_log.record("approve_document", "approval_tasks", task.id, task.approver_id,
                              {"task_status": task.task_status.value,
                               "review_comment": task.review_comment})

    def _change_status(self, document: FinancialDocument, to_status: DocumentStatus,
                       operator_id: int | None, remark: str | None = None) -> DocumentStatusLog:
        """按 PRD 7.3 流转表变更单据状态：校验合法性、追加留痕并推送 document_status。"""
        # 步骤 1：取变更前状态，作为流转合法性与留痕的基准（PRD 7.3）
        current = document.document_status
        # 步骤 2：查表校验——非法流转直接报错，确定性判定，不交大模型（PRD 20.1 P1）
        if to_status not in ALLOWED_TRANSITIONS[current]:
            raise ValueError("PRD 7.3 不允许从 %s 流转到 %s" % (current, to_status))
        # 步骤 3：构造状态留痕，记录前后状态、操作人、备注与时间（PRD 7.2 状态变化留痕）
        log = DocumentStatusLog(id=0, document_id=document.id, from_status=current,
                                to_status=to_status, operator_id=operator_id, remark=remark,
                                created_at=datetime.now(timezone.utc))
        # 步骤 4：回写单据状态与最近更新时间
        document.document_status, document.updated_at = to_status, log.created_at
        # 步骤 5：追加到状态留痕列表——只增不改（PRD 20.1 P7）
        self.status_logs.append(log)
        # 步骤 6：推送 document_status 消息，携带单据主键、新状态与当前版本号（PRD 14.2）
        self.publisher.publish("document_status",
                               DocumentStatusMessage(document.id, to_status,
                                                     document.current_version or 0))
        # 步骤 7：返回留痕记录，供调用方落库
        return log
