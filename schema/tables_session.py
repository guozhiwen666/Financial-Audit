"""审核会话表结构（PRD 2.7.10、2.7.6）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
"""

from dataclasses import dataclass        # dataclass：声明纯字段结构
from datetime import datetime            # datetime：会话创建/更新时间戳

from schema.enums import DocumentType    # DocumentType：会话中已确认的单据类型

__all__ = [
    "ReviewSession",     # 审核会话表
    "SessionMessage",    # 会话消息表
]


@dataclass
class ReviewSession:
    """review_sessions 表：一次多轮审核会话的上下文主体。"""

    id: int                                        # 主键
    user_id: int | None = None                     # 发起会话的用户，指向 users.id
    document_type: DocumentType | None = None       # 会话中已确认的单据类型（确认后不再重复询问）
    document_no: str | None = None                  # 会话中已确认的单据编号（确认后不再重复询问）
    session_status: str | None = None               # 会话状态（PRD 未列举取值，保持字符串）
    created_at: datetime | None = None              # 会话创建时间
    updated_at: datetime | None = None              # 最近一次更新时间


@dataclass
class SessionMessage:
    """session_messages 表：会话消息流水，用于回放多轮交互过程。"""

    id: int                                        # 主键
    session_id: int | None = None                  # 所属会话主键，指向 review_sessions.id
    role: str | None = None                        # 消息发出方（用户/系统）
    content: str | None = None                     # 消息内容
    message_type: str | None = None                # 消息类型（PRD 未列举取值，保持字符串）
    created_at: datetime | None = None             # 消息产生时间
