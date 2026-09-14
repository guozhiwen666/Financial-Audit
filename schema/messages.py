"""实时消息结构（PRD 2.7.12）。

字段与 PRD 列举逐项一致。消息为事件载荷，字段全部必填，不设默认值。
"""

from dataclasses import dataclass
from datetime import datetime

from schema.enums import (
    AnalysisTaskStatus,
    ApprovalTaskStatus,
    AttachmentParseStatus,
    AttachmentStorageStatus,
    DocumentStatus,
    RiskLevel,
)

__all__ = [
    "DocumentStatusMessage",
    "ApprovalStatusMessage",
    "SlotRequiredMessage",
    "TaskStatusMessage",
    "AttachmentStatusMessage",
    "RiskFindingMessage",
    "ReportReadyMessage",
    "ErrorMessage",
    "DoneMessage",
]


@dataclass
class DocumentStatusMessage:
    """document_status 消息。"""

    document_id: int
    document_status: DocumentStatus
    current_version: int


@dataclass
class ApprovalStatusMessage:
    """approval_status 消息。"""

    document_id: int
    instance_id: int
    node_id: int
    task_status: ApprovalTaskStatus


@dataclass
class SlotRequiredMessage:
    """slot_required 消息：多轮交互请求补齐槽位。"""

    session_id: int
    slot_name: str
    question_text: str
    candidate_values: list[str]


@dataclass
class TaskStatusMessage:
    """task_status 消息：分析任务进度。"""

    task_id: int
    task_status: AnalysisTaskStatus
    current_step: str
    progress: int


@dataclass
class AttachmentStatusMessage:
    """attachment_status 消息。"""

    attachment_id: int
    storage_status: AttachmentStorageStatus
    parse_status: AttachmentParseStatus


@dataclass
class RiskFindingMessage:
    """risk_finding 消息。"""

    task_id: int
    finding_id: int
    risk_type: str
    risk_level: RiskLevel
    risk_title: str


@dataclass
class ReportReadyMessage:
    """report_ready 消息。"""

    task_id: int
    report_id: int
    overall_risk_level: RiskLevel


@dataclass
class ErrorMessage:
    """error 消息。"""

    task_id: int
    error_code: str
    error_message: str


@dataclass
class DoneMessage:
    """done 消息。"""

    task_id: int
    finished_at: datetime
