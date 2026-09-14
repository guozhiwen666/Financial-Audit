"""审批流程与状态留痕表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
"""

from dataclasses import dataclass        # dataclass：声明纯字段结构
from datetime import datetime            # datetime：审批过程时间戳
from typing import Any                   # Any：JSON 列内的值类型不固定

from schema.enums import (
    ApprovalInstanceStatus,              # 审批实例状态
    ApprovalTaskStatus,                  # 审批任务状态
    DocumentStatus,                      # 单据状态（状态留痕的前后状态）
    DocumentType,                        # 单据类型（流程适用条件）
)

__all__ = [
    "ApprovalWorkflow",         # 审批流程定义表
    "ApprovalWorkflowNode",     # 审批节点定义表
    "ApprovalInstance",         # 审批实例表
    "ApprovalTask",             # 审批任务表
    "DocumentStatusLog",        # 单据状态留痕表
]


@dataclass
class ApprovalWorkflow:
    """approval_workflows 表：审批流程定义。"""

    id: int                                                  # 主键
    workflow_name: str | None = None                          # 流程名称，展示用
    document_type: DocumentType | None = None                 # 适用的单据类型
    match_conditions_json: dict[str, Any] | None = None       # 适用条件（金额区间、部门等匹配规则）
    status: str | None = None                                 # 流程状态（PRD 未列举取值，保持字符串）
    created_at: datetime | None = None                        # 创建时间
    updated_at: datetime | None = None                        # 最近一次更新时间


@dataclass
class ApprovalWorkflowNode:
    """approval_workflow_nodes 表：审批节点定义。"""

    id: int                                        # 主键
    workflow_id: int | None = None                 # 所属流程主键，指向 approval_workflows.id
    node_name: str | None = None                   # 节点名称（如部门经理审批）
    node_order: int | None = None                  # 节点顺序，决定审批先后
    approver_role: str | None = None               # 该节点的审批角色
    approval_mode: str | None = None               # 审批模式（单人/会签等，取值 PRD 未列举）
    created_at: datetime | None = None             # 创建时间


@dataclass
class ApprovalInstance:
    """approval_instances 表：单据的一次审批实例。"""

    id: int                                                       # 主键
    workflow_id: int | None = None                                # 所用流程主键，指向 approval_workflows.id
    document_id: int | None = None                                # 所属单据主键，指向 financial_documents.id
    document_version: int | None = None                           # 该实例对应的单据版本号
    instance_status: ApprovalInstanceStatus | None = None          # 实例状态（流转中/已通过等）
    current_node_id: int | None = None                            # 当前所处节点主键，指向 approval_workflow_nodes.id
    started_at: datetime | None = None                            # 实例启动时间
    finished_at: datetime | None = None                           # 实例结束时间（未结束时为空）


@dataclass
class ApprovalTask:
    """approval_tasks 表：单个审批节点的待办任务。"""

    id: int                                                # 主键
    instance_id: int | None = None                          # 所属实例主键，指向 approval_instances.id
    node_id: int | None = None                              # 对应节点主键，指向 approval_workflow_nodes.id
    approver_id: int | None = None                          # 审批人用户主键，指向 users.id
    task_status: ApprovalTaskStatus | None = None           # 任务状态（待处理/通过/退回/驳回等）
    review_comment: str | None = None                       # 审批意见
    created_at: datetime | None = None                      # 任务生成时间
    processed_at: datetime | None = None                    # 处理完成时间（未处理时为空）


@dataclass
class DocumentStatusLog:
    """document_status_logs 表：单据状态流转留痕。"""

    id: int                                        # 主键
    document_id: int | None = None                 # 所属单据主键，指向 financial_documents.id
    from_status: DocumentStatus | None = None       # 变更前的单据状态
    to_status: DocumentStatus | None = None         # 变更后的单据状态
    operator_id: int | None = None                 # 操作人用户主键，指向 users.id
    remark: str | None = None                      # 变更备注（如撤回/作废原因）
    created_at: datetime | None = None             # 变更时间
