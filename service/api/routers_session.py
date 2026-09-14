"""审核会话接口（PRD 13.5 审核会话）。

覆盖：创建会话、发送消息（返回澄清问题或分析任务信息）、查询历史消息。
多轮交互的澄清与槽位确认由 A1 会话编排智能体完成（PRD 8.1、20.2）。
"""

from typing import Annotated

from fastapi import APIRouter, Body

from service.business_services import session_service
from service.api.deps import CurrentPrincipal
from service.api.serializers import as_dict, as_list

__all__ = ["router"]

router = APIRouter(tags=["审核会话"])


@router.post("/review-sessions")
def create_session(payload: Annotated[dict, Body()], principal: CurrentPrincipal) -> dict:
    """创建审核会话（PRD 13.5 POST /review-sessions）。"""
    session = session_service.create_session(principal.user_id, payload)
    return {"session": as_dict(session)}


@router.post("/review-sessions/{session_id}/messages")
def send_message(session_id: int, payload: Annotated[dict, Body()],
                 principal: CurrentPrincipal) -> dict:
    """发送消息并返回澄清问题或分析任务信息（PRD 13.5 POST /review-sessions/{id}/messages）。"""
    # 步骤 1：交服务层驱动多轮交互图——A1 抽取槽位、追问缺失项、单据确认后进入分析段（PRD 8.2）
    result = session_service.send_message(session_id, payload.get("content") or "",
                                          principal.role_codes, principal.user_id)
    state = result["state"]
    # 步骤 2：返回会话、助手回复、槽位与分析任务信息；实时消息供前端展示进度
    return {"session": as_dict(result["session"]), "reply": result["reply"],
            "slots": state.get("slots") or {},
            "analysis_task": as_dict(state.get("analysis_task")),
            "report": as_dict(state.get("report")),
            "findings": as_list(state.get("findings") or []),
            "messages": as_list(result["messages"])}


@router.get("/review-sessions/{session_id}/messages")
def list_messages(session_id: int, principal: CurrentPrincipal) -> dict:
    """查询会话历史消息（PRD 13.5 GET /review-sessions/{session_id}/messages）。"""
    messages = session_service.list_messages(session_id, principal.role_codes, principal.user_id)
    return {"items": as_list(messages), "total": len(messages)}
