"""状态与等级枚举。

只收录 PRD 中**明确列举了取值**的枚举（2.7.2 单据类型、2.7.12 各状态与等级、
2.7.13 处理建议）。PRD 未列举取值的字段（如 ``users.status``、``session_status``、
``approval_mode``、``item_type``、``action_type`` 等）在表结构中保持 ``str``，不在此臆造。
"""

from enum import Enum

__all__ = [
    "DocumentType",
    "DocumentStatus",
    "ApprovalInstanceStatus",
    "ApprovalTaskStatus",
    "AttachmentStorageStatus",
    "AttachmentParseStatus",
    "AnalysisTaskStatus",
    "RiskLevel",
    "RiskReviewStatus",
    "Recommendation",
]


class DocumentType(str, Enum):
    """单据类型（PRD 2.7.2 五类主要单据）。"""

    PUBLIC_PAYMENT = "对公付款单"
    ADVANCE_PAYMENT = "预付款单"
    BATCH_PAYMENT = "批量付款单"
    EXPENSE_REIMBURSEMENT = "费用报销单"
    TRAVEL_REIMBURSEMENT = "差旅报销单"


class DocumentStatus(str, Enum):
    """单据状态（PRD 2.7.12）。"""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    REVIEWING = "reviewing"
    RETURNED = "returned"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    VOIDED = "voided"


class ApprovalInstanceStatus(str, Enum):
    """审批实例状态（PRD 2.7.12）。"""

    PENDING = "pending"
    RUNNING = "running"
    APPROVED = "approved"
    RETURNED = "returned"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalTaskStatus(str, Enum):
    """审批任务状态（PRD 2.7.12）。"""

    PENDING = "pending"
    APPROVED = "approved"
    RETURNED = "returned"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class AttachmentStorageStatus(str, Enum):
    """附件存储状态（PRD 2.7.12）。"""

    UPLOADING = "uploading"
    STORED = "stored"
    FAILED = "failed"


class AttachmentParseStatus(str, Enum):
    """附件解析状态（PRD 2.7.12）。"""

    PENDING = "pending"
    PARSING = "parsing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class AnalysisTaskStatus(str, Enum):
    """分析任务状态（PRD 2.7.12）。"""

    QUEUED = "queued"
    QUERYING_DOCUMENT = "querying_document"
    LOADING_ATTACHMENTS = "loading_attachments"
    PARSING_ATTACHMENTS = "parsing_attachments"
    ANALYZING = "analyzing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    """风险等级（PRD 2.7.7）。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskReviewStatus(str, Enum):
    """风险项复核状态（PRD 2.7.12）。"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


class Recommendation(str, Enum):
    """处理建议（PRD 2.7.13）。"""

    APPROVE = "建议通过"
    SUPPLEMENT = "补充材料"
    MANUAL_REVIEW = "人工复核"
    REJECT = "建议驳回"
