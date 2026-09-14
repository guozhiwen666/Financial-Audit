"""单据与明细接口（PRD 13.2 单据、13.3 明细）。

覆盖：单据创建、列表查询、详情、编辑、复制、提交、撤回、作废，以及明细的新增、更新、删除。
提交与作废类写操作按 PRD 13.10 接收 ``Idempotency-Key`` 请求头，防止重复任务（PRD 11.1）。
"""

from typing import Annotated

from fastapi import APIRouter, Body, Header, Query

from service.infrastructure import idempotency
from service.business_services import document_service, line_item_service
from service.api.deps import CurrentPrincipal
from service.api.serializers import as_dict, as_list
from service.infrastructure.errors import BadRequest

__all__ = ["router"]

router = APIRouter(tags=["单据"])


@router.post("/documents")
def create_document(payload: Annotated[dict, Body()], principal: CurrentPrincipal) -> dict:
    """创建单据（PRD 13.2 POST /documents）。"""
    # 步骤 1：申请人与申请部门取自登录主体与请求体，交服务层建单并落库
    department = payload.get("applicant_department")
    if not department:
        raise BadRequest("缺少必填字段 applicant_department（PRD 5.2）")
    document = document_service.create(principal.user_id, department, payload)
    return {"document": as_dict(document)}


@router.get("/documents")
def list_documents(principal: CurrentPrincipal,
                   document_type: str | None = None, applicant_id: int | None = None,
                   department: str | None = None, document_status: str | None = None,
                   document_no: str | None = None, start_date: str | None = None,
                   end_date: str | None = None, page: int = Query(default=1, ge=1),
                   page_size: int = Query(default=20, ge=1, le=200)) -> dict:
    """按单据类型、申请人、部门、状态和日期查询单据列表（PRD 13.2 GET /documents）。"""
    # 步骤 1：汇总筛选条件，交服务层在 SQL 层收敛数据权限（PRD 11.1 权限前置）
    filters = {"document_type": document_type, "applicant_id": applicant_id,
               "department": department, "document_status": document_status,
               "document_no": document_no, "start_date": start_date, "end_date": end_date}
    rows, total = document_service.list_documents(principal.role_codes, principal.user_id,
                                                  filters, page, page_size)
    # 步骤 2：按 PRD 13.10 返回 total 与分页信息
    return {"total": total, "page": page, "page_size": page_size, "items": as_list(rows)}


@router.get("/documents/{document_id}")
def get_document(document_id: int, principal: CurrentPrincipal) -> dict:
    """查询单据详情、明细、附件、版本和审批进度（PRD 13.2 GET /documents/{document_id}）。"""
    detail = document_service.detail(document_id, principal.role_codes, principal.user_id)
    return {key: (as_list(value) if isinstance(value, list) else as_dict(value))
            for key, value in detail.items()}


@router.patch("/documents/{document_id}")
def update_document(document_id: int, payload: Annotated[dict, Body()],
                    principal: CurrentPrincipal) -> dict:
    """编辑草稿或退回状态的单据（PRD 13.2 PATCH /documents/{document_id}）。"""
    document = document_service.update(document_id, payload, principal.role_codes,
                                       principal.user_id)
    return {"document": as_dict(document)}


@router.post("/documents/{document_id}/copy")
def copy_document(document_id: int, principal: CurrentPrincipal) -> dict:
    """复制单据并生成新草稿（PRD 13.2 POST /documents/{document_id}/copy）。"""
    draft = document_service.copy_document(document_id, principal.role_codes, principal.user_id)
    return {"document": as_dict(draft)}


@router.post("/documents/{document_id}/submit")
def submit_document(document_id: int, principal: CurrentPrincipal,
                    idempotency_key: Annotated[str, Header()] = "") -> dict:
    """提交单据并创建审批实例和分析任务（PRD 13.2 POST submit、11.1 幂等性）。"""
    # 步骤 1：按幂等键执行，重复提交返回首次结果，不产生重复实例与任务
    result = idempotency.run_once(idempotency_key, "submit:%s" % document_id,
                                  lambda: document_service.submit(document_id,
                                                                  principal.role_codes,
                                                                  principal.user_id))
    return {"document": as_dict(result["document"]), "snapshot": as_dict(result["snapshot"]),
            "instance": as_dict(result["instance"]), "task": as_dict(result["task"])}


@router.post("/documents/{document_id}/withdraw")
def withdraw_document(document_id: int, principal: CurrentPrincipal) -> dict:
    """撤回未处理的单据（PRD 13.2 POST /documents/{document_id}/withdraw）。"""
    document = document_service.withdraw(document_id, principal.role_codes, principal.user_id)
    return {"document": as_dict(document)}


@router.post("/documents/{document_id}/void")
def void_document(document_id: int, principal: CurrentPrincipal) -> dict:
    """作废符合条件的单据（PRD 13.2 POST /documents/{document_id}/void）。"""
    document = document_service.void(document_id, principal.role_codes, principal.user_id)
    return {"document": as_dict(document)}


@router.post("/documents/{document_id}/line-items")
def add_line_item(document_id: int, payload: Annotated[dict, Body()],
                  principal: CurrentPrincipal) -> dict:
    """新增单据明细（PRD 13.3 POST /documents/{document_id}/line-items）。"""
    item = line_item_service.add_line_item(document_id, payload, principal.role_codes,
                                           principal.user_id)
    return {"line_item": as_dict(item)}


@router.patch("/documents/{document_id}/line-items/{line_item_id}")
def update_line_item(document_id: int, line_item_id: int, payload: Annotated[dict, Body()],
                     principal: CurrentPrincipal) -> dict:
    """更新单据明细（PRD 13.3 PATCH /documents/{document_id}/line-items/{line_item_id}）。"""
    item = line_item_service.update_line_item(document_id, line_item_id, payload,
                                              principal.role_codes, principal.user_id)
    return {"line_item": as_dict(item)}


@router.delete("/documents/{document_id}/line-items/{line_item_id}")
def delete_line_item(document_id: int, line_item_id: int, principal: CurrentPrincipal) -> dict:
    """删除单据明细（PRD 13.3 DELETE /documents/{document_id}/line-items/{line_item_id}）。"""
    affected = line_item_service.delete_line_item(document_id, line_item_id,
                                                  principal.role_codes, principal.user_id)
    return {"deleted": affected}
