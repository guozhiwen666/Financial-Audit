"""审批接口（PRD 13.7 审批）。

覆盖：查询当前用户的审批任务、通过 / 退回 / 驳回审批任务，以及审批流程的查询、创建与更新。
审批结论由有权限的人员人工确认（PRD 2.7.14），状态流转由环节三按 PRD 7.3 流转表执行。
"""

from typing import Annotated

from fastapi import APIRouter, Body, Header

from service.infrastructure import idempotency
from service.business_services import approval_service
from service.api.deps import CurrentPrincipal
from service.api.serializers import as_dict

__all__ = ["router"]

router = APIRouter(tags=["审批"])


@router.get("/approval-tasks")
def list_tasks(principal: CurrentPrincipal, status: str | None = None) -> dict:
    """查询当前用户的审批任务（PRD 13.7 GET /approval-tasks）。"""
    tasks = approval_service.list_tasks(principal.role_codes, principal.user_id, status)
    return {"items": [as_dict(task) for task in tasks], "total": len(tasks)}


@router.post("/approval-tasks/{task_id}/approve")
def approve(task_id: int, principal: CurrentPrincipal,
            payload: Annotated[dict, Body()] = None,
            idempotency_key: Annotated[str, Header()] = "") -> dict:
    """通过审批任务（PRD 13.7 POST approve、11.1 幂等性）。"""
    # 步骤 1：按幂等键执行，重复请求不产生重复审批动作（PRD 11.1）
    result = idempotency.run_once(
        idempotency_key, "approve:%s" % task_id,
        lambda: approval_service.approve(task_id, principal.role_codes, principal.user_id,
                                         (payload or {}).get("review_comment")))
    return _approval_response(result)


@router.post("/approval-tasks/{task_id}/return")
def return_back(task_id: int, principal: CurrentPrincipal,
                payload: Annotated[dict, Body()] = None,
                idempotency_key: Annotated[str, Header()] = "") -> dict:
    """退回审批任务（PRD 13.7 POST return）。"""
    result = idempotency.run_once(
        idempotency_key, "return:%s" % task_id,
        lambda: approval_service.return_back(task_id, principal.role_codes, principal.user_id,
                                             (payload or {}).get("review_comment")))
    return _approval_response(result)


@router.post("/approval-tasks/{task_id}/reject")
def reject(task_id: int, principal: CurrentPrincipal,
           payload: Annotated[dict, Body()] = None,
           idempotency_key: Annotated[str, Header()] = "") -> dict:
    """驳回审批任务（PRD 13.7 POST reject）。"""
    result = idempotency.run_once(
        idempotency_key, "reject:%s" % task_id,
        lambda: approval_service.reject(task_id, principal.role_codes, principal.user_id,
                                        (payload or {}).get("review_comment")))
    return _approval_response(result)


def _approval_response(result: dict) -> dict:
    """统一审批动作的响应体：任务、下一节点任务、实例与单据状态。"""
    return {"task": as_dict(result["task"]), "next_task": as_dict(result["next_task"]),
            "instance": as_dict(result["instance"]), "document": as_dict(result["document"])}


@router.get("/approval-workflows")
def list_workflows(principal: CurrentPrincipal) -> dict:
    """查询审批流程（PRD 13.7 GET /approval-workflows）。"""
    workflows = approval_service.list_workflows()
    return {"items": [as_dict(workflow) for workflow in workflows], "total": len(workflows)}


@router.post("/approval-workflows")
def create_workflow(payload: Annotated[dict, Body()], principal: CurrentPrincipal) -> dict:
    """创建审批流程（PRD 13.7 POST /approval-workflows）。"""
    result = approval_service.create_workflow(payload, principal.role_codes)
    return {"workflow": as_dict(result["workflow"])}


@router.patch("/approval-workflows/{workflow_id}")
def update_workflow(workflow_id: int, payload: Annotated[dict, Body()],
                    principal: CurrentPrincipal) -> dict:
    """更新审批流程（PRD 13.7 PATCH /approval-workflows/{workflow_id}）。"""
    workflow = approval_service.update_workflow(workflow_id, payload, principal.role_codes)
    return {"workflow": as_dict(workflow)}
