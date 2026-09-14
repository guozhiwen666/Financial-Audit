"""会话模块（PRD 11 章「会话模块」、第 8 章、13.5）。

职责：审核会话、消息记录、槽位状态与多轮上下文管理。
边界：多轮交互的识别、抽取与追问由 A1 会话编排智能体负责（PRD 20.2）；
本模块只负责取数与落库，并按 PRD 8.1 第 4 条保证已确认槽位不被重复询问。
"""

from datetime import datetime, timezone  # 消息与槽位时间戳

from schema.tables_session import ReviewSession, SessionMessage, SessionSlot  # 会话实体
from service.infrastructure import repository as repo, runtime
from service.business_services import analysis_service, auth_service
from service.infrastructure.database import transaction
from service.infrastructure.errors import BadRequest, NotFound, PermissionDenied

__all__ = ["create_session", "require_session", "list_messages", "send_message"]

# 会话状态取值：PRD 未列举 session_status 的取值集合（schema/ 亦保守处理为 str），
# 故此处约定 active 表示会话进行中，不臆造完整状态机。
SESSION_ACTIVE = "active"


def create_session(user_id: int, payload: dict) -> ReviewSession:
    """创建审核会话（PRD 13.5 POST /review-sessions）。"""
    # 步骤 1：会话可携带初始单据类型与编号（PRD 2.7.10 review_sessions 字段）
    session = ReviewSession(id=0, user_id=user_id,
                            document_type=repo.review_sessions.coerce(
                                "document_type", payload.get("document_type")),
                            document_no=payload.get("document_no"),
                            session_status=SESSION_ACTIVE,
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc))
    # 步骤 2：落库并回填主键
    session.id = repo.review_sessions.insert(session)
    # 步骤 3：初始槽位一并落库，保证刷新页面后不重复询问（PRD 8.1 第 4 条、8.3）
    for name in ("document_type", "document_no"):
        value = getattr(session, name)
        if value:
            _save_slot(session.id, name, value)
    return session


def require_session(session_id: int, role_codes: list[str], user_id: int) -> ReviewSession:
    """取会话并校验归属（PRD 3.3 数据权限）。"""
    # 步骤 1：会话必须存在
    session = repo.review_sessions.get(session_id)
    if session is None:
        raise NotFound("审核会话不存在：%s" % session_id)
    # 步骤 2：会话是用户私有上下文——仅创建者本人可访问
    if session.user_id != user_id:
        raise PermissionDenied("无权访问该会话")
    return session


def _load_slots(session_id: int) -> dict[str, str]:
    """载入会话已确认的槽位（PRD 8.3 槽位状态持久化）。"""
    return {slot.slot_name: slot.slot_value
            for slot in repo.session_slots.find("session_id = %s", (session_id,))
            if slot.slot_value}


def _save_slot(session_id: int, slot_name: str, slot_value: str) -> None:
    """写入或更新槽位；已确认的槽位不重复询问，故一律置为已确认（PRD 8.1 第 4 条）。"""
    # 步骤 1：同一会话同一槽位只保留一条记录
    existing = repo.session_slots.find("session_id = %s AND slot_name = %s",
                                       (session_id, slot_name), limit=1)
    now = datetime.now(timezone.utc)
    if existing:
        repo.session_slots.update(existing[0].id, slot_value=slot_value, is_confirmed=True,
                                  updated_at=now)
        return
    # 步骤 2：首次出现则新建
    repo.session_slots.insert(SessionSlot(id=0, session_id=session_id, slot_name=slot_name,
                                          slot_value=slot_value, is_confirmed=True, updated_at=now))


def list_messages(session_id: int, role_codes: list[str], user_id: int) -> list:
    """查询会话历史消息（PRD 13.5 GET /review-sessions/{id}/messages）。"""
    require_session(session_id, role_codes, user_id)
    return repo.session_messages.find("session_id = %s", (session_id,), order="id")


def _save_message(session_id: int, role: str, content: str, message_type: str) -> SessionMessage:
    """保存一条会话消息（PRD 2.7.10 session_messages）。"""
    message = SessionMessage(id=0, session_id=session_id, role=role, content=content,
                             message_type=message_type, created_at=datetime.now(timezone.utc))
    message.id = repo.session_messages.insert(message)
    return message


def send_message(session_id: int, content: str, role_codes: list[str], user_id: int) -> dict:
    """发送消息并返回澄清问题或分析任务信息（PRD 13.5 POST /review-sessions/{id}/messages）。"""
    # 步骤 1：会话归属校验，并校验内容非空
    session = require_session(session_id, role_codes, user_id)
    if not content:
        raise BadRequest("消息内容不能为空")
    # 步骤 2：保存用户消息，形成完整对话流水（PRD 2.7.10）
    _save_message(session_id, "user", content, "text")
    # 步骤 3：载入已确认槽位并回填到会话实体，A1 据此不再重复询问（PRD 8.1 第 4 条）
    slots = _load_slots(session_id)
    session.document_type = session.document_type or _as_document_type(slots.get("document_type"))
    session.document_no = session.document_no or slots.get("document_no")
    # 步骤 4：按「单据类型 + 单据编号」查询单据，并判定数据权限（PRD 8.1 第 6 条）
    document, has_permission = _query_document(session, role_codes, user_id)
    # 步骤 5：驱动多轮交互图——A1 抽取槽位、追问缺失项、并在单据确认后进入分析段（PRD 8.2）
    with transaction():
        state = runtime.flow().run_intake({
            "session": session, "user_message": content, "document": document,
            "has_permission": has_permission, "task_id": 0,
            "line_items": (repo.document_line_items.find("document_id = %s", (document.id,),
                                                         order="id") if document else []),
            "attachments": (repo.document_attachments.find("document_id = %s",
                                                           (document.id,), order="id")
                            if document else []),
        })
        # 步骤 6：A1 产出的槽位落库，供后续轮次复用（PRD 8.3 槽位状态持久化）
        for name, value in (state.get("slots") or {}).items():
            if value:
                _save_slot(session_id, name, value)
        # 步骤 7：分析产出落库（仅当单据确认并进入分析段时才有产出）
        if state.get("analysis_task") is not None:
            analysis_service.persist(state)
    # 步骤 8：更新会话上已确认的单据类型与编号
    repo.review_sessions.update(session_id,
                                document_type=session.document_type,
                                document_no=slots.get("document_no") or session.document_no,
                                updated_at=datetime.now(timezone.utc))
    # 步骤 9：报告就绪后由编排层调用 A1 完成汇总与 done（PRD 8.1 O/P 步）
    if state.get("analysis_task") is not None:
        runtime.flow().orchestrator.step6_summarize(state["analysis_task"].id, state.get("report"))
    # 步骤 10：保存助手回复并连同实时消息一并返回
    reply = state.get("summary") or ""
    _save_message(session_id, "assistant", reply, "text")
    return {"session": session, "reply": reply, "state": state,
            "messages": runtime.messages_since(0)}


def _as_document_type(value):
    """把槽位取值转为单据类型枚举；取值非法时返回 None（不臆造类型）。"""
    if not value:
        return None
    try:
        return repo.review_sessions.coerce("document_type", value)
    except ValueError:
        return None


def _query_document(session, role_codes: list[str], user_id: int):
    """按槽位查询单据并判定权限，返回 (单据或 None, 是否有权限)（PRD 8.1 第 6 条）。"""
    # 步骤 1：槽位不全则无法查询，交由 A1 追问
    if not (session.document_type and session.document_no):
        return None, False
    # 步骤 2：按单据类型 + 单据编号精确定位单据
    rows = repo.financial_documents.find("document_type = %s AND document_no = %s",
                                         (session.document_type.value, session.document_no),
                                         limit=1)
    if not rows:
        return None, False
    document = rows[0]
    # 步骤 3：数据权限判定（PRD 3.3、8.1 第 7 条：只能分析权限范围内的单据）
    if not auth_service.can_view_document(role_codes, user_id, document):
        return document, False
    return document, True
