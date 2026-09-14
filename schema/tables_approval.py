"""审批流程与状态留痕表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from schema.enums import (
    ApprovalInstanceStatus,
    ApprovalTaskStatus,
    DocumentStatus,
    DocumentType,
)

__all__ = [
    "ApprovalWorkflow",
    "ApprovalWorkflowNode",
    "ApprovalInstance",
    "ApprovalTask",
    "DocumentStatusLog",
]


@dataclass
class ApprovalWorkflow:
    """approval_workflows 表：审批流程定义。"""

    id: int
    workflow_name: str | None = None
    document_type: DocumentType | None = None
    match_conditions_json: dict[str, Any] | None = None
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ApprovalWorkflowNode:
    """approval_workflow_nodes 表：审批节点定义。"""

    id: int
    workflow_id: int | None = None
    node_name: str | None = None
    node_order: int | None = None
    approver_role: str | None = None
    approval_mode: str | None = None
    created_at: datetime | None = None


@dataclass
class ApprovalInstance:
    """approval_instances 表：单据的审批实例。"""

    id: int
    workflow_id: int | None = None
    document_id: int | None = None
    document_version: int | None = None
    instance_status: ApprovalInstanceStatus | None = None
    current_node_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass
class ApprovalTask:
    """approval_tasks 表：审批任务。"""

    id: int
    instance_id: int | None = None
    node_id: int | None = None
    approver_id: int | None = None
    task_status: ApprovalTaskStatus | None = None
    review_comment: str | None = None
    created_at: datetime | None = None
    processed_at: datetime | None = None


@dataclass
class DocumentStatusLog:
    """document_status_logs 表：单据状态流转留痕。"""

    id: int
    document_id: int | None = None
    from_status: DocumentStatus | None = None
    to_status: DocumentStatus | None = None
    operator_id: int | None = None
    remark: str | None = None
    created_at: datetime | None = None
