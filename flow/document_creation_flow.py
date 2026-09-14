"""环节一 单据创建（PRD 2.7.1 单据能力、7.2、7.3、5.2、5.3）。

职责：单据的创建、编辑、复制、提交、撤回与作废；提交校验；状态流转与状态留痕。
本环节对应后端「单据模块」（PRD 2.7.9），**是 document_status 消息的出口**（PRD 20.3）。

边界与约定：
* 金额一律 ``Decimal``，禁止 float（PRD 20.1 P1：金额计算必须确定性）；
* 状态流转必须按 PRD 7.3 的表校验，非法流转直接报错，不允许静默丢弃；
* 字段校验（5.2 必填）与合计校验（5.3 字段级约束）均为确定性逻辑，禁止交给大模型；
* 数据持久化未实现，故本环节只产出领域实体，主键以 0 占位待落库回填。
"""

from dataclasses import asdict, replace  # asdict：生成单据快照；replace：复制单据
from datetime import datetime, timezone  # 状态流转与留痕时间戳（PRD 12.2：时间戳统一 UTC）
from decimal import Decimal  # 金额与比例，禁止 float 以免精度丢失

from agent.utils.message import MessagePublisher  # 实时消息推送（PRD 14.2）
from flow.audit_log_flow import AuditLogFlow  # 环节七 操作审计：本环节写单据操作留痕
from flow.status_transitions import ALLOWED_TRANSITIONS  # PRD 7.3 状态流转表（与环节三共用）
from schema.enums import (  # 单据状态与单据类型、审批实例状态与审批任务状态
    ApprovalInstanceStatus, ApprovalTaskStatus, DocumentStatus, DocumentType,
)
from schema.messages import ApprovalStatusMessage, DocumentStatusMessage  # 状态变化消息（PRD 14.2）
from schema.tables_approval import (  # 审批实例、审批任务、审批节点定义、单据状态留痕
    ApprovalInstance, ApprovalTask, ApprovalWorkflowNode, DocumentStatusLog,
)
from schema.tables_document import (  # 单据主表、版本快照、明细行
    DocumentLineItem, DocumentVersion, FinancialDocument,
)

__all__ = ["DocumentCreationFlow"]

# PRD 5.2 标注「必填」的共有结构化字段（申请人对应 FinancialDocument.applicant_id）
REQUIRED_FIELDS = ("document_type", "document_no", "applicant_id", "applicant_department",
                   "total_amount", "currency", "apply_date")
# PRD 5.3 差旅报销单的费用构成：交通费 + 住宿费 + 餐费 + 补贴 之和须等于总金额
TRAVEL_FEE_FIELDS = ("transport_fee", "accommodation_fee", "meal_fee", "allowance")


class DocumentCreationFlow:
    """环节一 单据创建（PRD 2.7.1 单据能力、7.3）。"""

    def __init__(self, publisher: MessagePublisher, audit_log: AuditLogFlow) -> None:
        """注入消息出口与审计环节。"""
        self.publisher = publisher  # document_status 消息由本环节推送（PRD 20.3）
        self.audit_log = audit_log  # 单据操作留痕（PRD 2.7.9 日志模块）
        self.status_logs: list[DocumentStatusLog] = []  # 本环节产生的状态留痕，随版本一并落库

    def create(self, document_type: DocumentType, applicant_id: int,
               department: str) -> FinancialDocument:
        """创建单据草稿：初始化单据类型、申请信息与状态，等待填写字段与明细（PRD 2.7.5）。"""
        # 步骤 1：取当前时间，同时作为创建时间与最近更新时间（时间戳统一 UTC，PRD 12.2）
        now = datetime.now(timezone.utc)
        # 步骤 2：构造草稿实体——主键以 0 占位待落库回填；币种按 PRD 5.2 默认 CNY；状态置 draft
        return FinancialDocument(id=0,
                                 document_type=document_type,          # 单据类型，五类之一（PRD 5.1）
                                 applicant_id=applicant_id,            # 申请人，指向 users.id
                                 applicant_department=department,      # 申请部门
                                 currency="CNY",                       # 币种默认 CNY（PRD 5.2）
                                 document_status=DocumentStatus.DRAFT,  # 草稿：可自由编辑
                                 created_at=now, updated_at=now)

    def update(self, document: FinancialDocument) -> FinancialDocument:
        """编辑草稿或退回状态的单据（PRD 13.2 编辑草稿或退回状态的单据）。"""
        # 步骤 1：状态闸口——仅 draft / returned 可编辑，其余状态一律拒绝（PRD 7.3）
        if document.document_status not in (DocumentStatus.DRAFT, DocumentStatus.RETURNED):
            raise ValueError("仅草稿或已退回的单据可编辑（PRD 7.3）：%s" % document.document_status)
        # 步骤 2：字段校验——PRD 5.3 把付款比例与出差起止日期的校验时机定在「保存草稿」
        self._validate_fields(document)
        # 步骤 3：刷新最近更新时间
        document.updated_at = datetime.now(timezone.utc)
        # 步骤 4：返回更新后的单据实体，供调用方落库
        return document

    def copy(self, document: FinancialDocument) -> FinancialDocument:
        """复制单据并生成新草稿：字段整体沿用，主键、编号与版本重置（PRD 2.7.11 复制单据）。"""
        # 步骤 1：以 replace 生成新实体，不改动入参单据（避免复制动作污染原单据）
        now = datetime.now(timezone.utc)
        # 步骤 2：清空主键与编号（PRD 5.2 单据编号系统内唯一，需重新生成）
        # 步骤 3：清空版本号（新草稿尚未提交，无版本快照）；状态重置为 draft；时间取当前
        return replace(document, id=0, document_no=None, current_version=None,
                       document_status=DocumentStatus.DRAFT, created_at=now, updated_at=now)

    def submit(self, document: FinancialDocument, line_items: list[DocumentLineItem],
               first_node: ApprovalWorkflowNode,
               approver_id: int) -> tuple[DocumentVersion, ApprovalInstance, ApprovalTask]:
        """提交单据：校验 → 生成快照与审批实例/首个任务 → 状态流转 draft→pending_review。

        依据 PRD 7.2 的提交校验、快照生成与实例创建；首个节点与审批人由后端匹配审批流程后传入。
        """
        # 步骤 1：字段校验——PRD 5.2 必填项 + 5.3 保存草稿即校验项，不通过则定位到具体字段
        self._validate_fields(document)
        # 步骤 2：合计校验——PRD 5.3 分类型合计口径（校验时机含「提交审批」）
        self._validate_totals(document, line_items)
        # 步骤 3：版本号递增——首次提交为 1，退回后重提递增（PRD 7.2 重新提交生成新版本）
        version_no = (document.current_version or 0) + 1
        document.current_version = version_no
        # 步骤 4：状态流转 draft → pending_review，并追加状态留痕、推送 document_status（PRD 7.3）
        self._change_status(document, DocumentStatus.PENDING_REVIEW, document.applicant_id, "提交审批")
        now = datetime.now(timezone.utc)
        # 步骤 5：生成单据快照——固化提交时的单据字段与全部明细（PRD 7.2 快照生成）
        snapshot = DocumentVersion(
            id=0, document_id=document.id, version_no=version_no, created_by=document.applicant_id,
            document_snapshot_json={"document": asdict(document),
                                    "line_items": [asdict(item) for item in line_items]},
            created_at=now)
        # 步骤 6：创建审批实例——流程与首个节点由后端按单据类型/金额区间/部门匹配后传入（PRD 7.2）
        instance = ApprovalInstance(id=0, workflow_id=first_node.workflow_id,
                                    document_id=document.id, document_version=version_no,
                                    instance_status=ApprovalInstanceStatus.RUNNING,
                                    current_node_id=first_node.id, started_at=now)
        # 步骤 7：创建首个审批任务——实例尚未落库，其主键同为 0 占位，落库后回填（PRD 20.1 P4）
        task = ApprovalTask(id=0, instance_id=instance.id, node_id=first_node.id,
                            approver_id=approver_id, task_status=ApprovalTaskStatus.PENDING,
                            created_at=now)
        # 步骤 8：首个任务生成即属审批状态变化，推送 approval_status 消息（PRD 14.2）
        self.publisher.publish("approval_status",
                               ApprovalStatusMessage(document.id, instance.id, task.node_id,
                                                     task.task_status))
        # 步骤 9：返回三件产出（快照 / 实例 / 首个任务），供调用方落库
        return snapshot, instance, task

    def withdraw(self, document: FinancialDocument) -> FinancialDocument:
        """撤回未处理的单据：pending_review → withdrawn，仅申请人可撤回（PRD 7.3）。"""
        # 步骤 1：按 PRD 7.3 校验并流转 pending_review → withdrawn，同步留痕与推送
        self._change_status(document, DocumentStatus.WITHDRAWN, document.applicant_id, "申请人撤回")
        # 步骤 2：返回状态已变更的单据实体
        return document

    def void(self, document: FinancialDocument) -> FinancialDocument:
        """作废符合条件的单据：draft / returned → voided（PRD 7.3）。"""
        # 步骤 1：按 PRD 7.3 校验并流转到 voided（终态），同步留痕与推送
        self._change_status(document, DocumentStatus.VOIDED, document.applicant_id, "申请人作废")
        # 步骤 2：返回状态已变更的单据实体
        return document

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

    @staticmethod
    def _validate_fields(document: FinancialDocument) -> None:
        """字段校验（PRD 5.2 必填项 + 5.3 保存草稿即校验项）；不通过则定位到具体字段。"""
        # 步骤 1：必填校验——逐个检查 PRD 5.2 标 ✅ 的字段，收集全部缺失项后一次性报出
        missing = [n for n in REQUIRED_FIELDS if getattr(document, n) is None]
        if missing:
            raise ValueError("提交校验未通过，缺失必填字段：%s（PRD 5.2）" % "、".join(missing))
        # 步骤 2：付款比例校验——取值须为 0~1 的小数，未填写（None）时不校验（PRD 5.3）
        if document.payment_ratio is not None and not 0 <= document.payment_ratio <= 1:
            raise ValueError("付款比例须为 0~1 的小数（PRD 5.3）：%s" % document.payment_ratio)
        # 步骤 3：出差起止日期校验——结束日期不得早于开始日期，两者缺一即跳过（PRD 5.3）
        if (document.travel_start_date and document.travel_end_date
                and document.travel_end_date < document.travel_start_date):
            raise ValueError("出差结束日期不得早于开始日期（PRD 5.3）")

    @staticmethod
    def _validate_totals(document: FinancialDocument, line_items: list[DocumentLineItem]) -> None:
        """分类型合计校验（PRD 5.3 字段级约束，校验时机含「提交审批」）；确定性计算。"""
        # 步骤 1：先算出明细行金额合计，作为批量付款单与费用报销单的比对依据
        line_total = sum((item.amount or Decimal(0) for item in line_items), Decimal(0))
        # 步骤 2：按单据类型取出 PRD 5.3 明确列举的合计口径；未列举的类型不做臆测
        kind = document.document_type
        checks: tuple = ()
        if kind is DocumentType.BATCH_PAYMENT:  # PRD 5.3 单笔金额合计、付款笔数
            checks = (("单笔金额合计", line_total, document.batch_total_amount),
                      ("付款笔数", len(line_items), document.payment_count))
        elif kind is DocumentType.EXPENSE_REIMBURSEMENT:  # PRD 5.3 费用明细合计
            checks = (("费用明细合计", line_total, document.total_amount),)
        elif kind is DocumentType.TRAVEL_REIMBURSEMENT:  # PRD 5.3 差旅费合计
            travel = sum((getattr(document, n) or Decimal(0) for n in TRAVEL_FEE_FIELDS), Decimal(0))
            checks = (("差旅费合计（交通费+住宿费+餐费+补贴）", travel, document.total_amount),)
        # 步骤 3：逐项比对「实际值」与「应有值」，不一致即抛错并给出双方取值（PRD 9.3 可解释性）
        for name, actual, expected in checks:
            if actual != expected:
                raise ValueError("%s 为 %s，与应有值 %s 不一致（PRD 5.3）" % (name, actual, expected))
