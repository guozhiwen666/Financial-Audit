"""审核会话表结构（PRD 2.7.10、2.7.6）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
"""

from dataclasses import dataclass
from datetime import datetime

from schema.enums import DocumentType

__all__ = ["ReviewSession", "SessionMessage"]


@dataclass
class ReviewSession:
    """review_sessions 表：一次多轮审核会话的上下文主体。"""

    id: int
    user_id: int | None = None
    document_type: DocumentType | None = None
    document_no: str | None = None
    session_status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class SessionMessage:
    """session_messages 表：会话消息流水。"""

    id: int
    session_id: int | None = None
    role: str | None = None
    content: str | None = None
    message_type: str | None = None
    created_at: datetime | None = None
