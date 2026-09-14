"""规则与参考数据接口（PRD 13.8 供应商、13.9 规则，以及日志查询）。

覆盖：审核规则的查询、创建与更新；供应商风险信息查询；市场价参考数据与操作日志查询。
规则变更必须记录操作人、操作时间与变更内容（PRD 2.7.14），由服务层写入 ``audit_logs``。
"""

from typing import Annotated

from fastapi import APIRouter, Body

from service.business_services import reference_service
from service.api.deps import CurrentPrincipal
from service.api.serializers import as_dict, as_list

__all__ = ["router"]

router = APIRouter(tags=["规则与参考数据"])


@router.get("/rules")
def list_rules(principal: CurrentPrincipal) -> dict:
    """查询审核规则（PRD 13.9 GET /rules）。"""
    rules = reference_service.list_rules(principal.role_codes)
    return {"items": as_list(rules), "total": len(rules)}


@router.post("/rules")
def create_rule(payload: Annotated[dict, Body()], principal: CurrentPrincipal) -> dict:
    """创建审核规则（PRD 13.9 POST /rules）。"""
    rule = reference_service.create_rule(payload, principal.role_codes, principal.user_id)
    return {"rule": as_dict(rule)}


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, payload: Annotated[dict, Body()],
                principal: CurrentPrincipal) -> dict:
    """更新审核规则（PRD 13.9 PATCH /rules/{rule_id}）。"""
    rule = reference_service.update_rule(rule_id, payload, principal.role_codes, principal.user_id)
    return {"rule": as_dict(rule)}


@router.get("/suppliers/{supplier_code}/risks")
def supplier_risks(supplier_code: str, principal: CurrentPrincipal) -> dict:
    """查询供应商风险信息（PRD 13.8 GET /suppliers/{supplier_code}/risks）。"""
    result = reference_service.supplier_risks(supplier_code, principal.role_codes,
                                              principal.user_id)
    return {"supplier": as_dict(result["supplier"]), "history": as_list(result["history"]),
            "findings": as_list(result["findings"])}


@router.get("/suppliers")
def list_suppliers(principal: CurrentPrincipal) -> dict:
    """查询供应商档案列表（PRD 2.7.4 供应商风险页）。"""
    suppliers = reference_service.list_suppliers(principal.role_codes)
    return {"items": as_list(suppliers), "total": len(suppliers)}


@router.get("/market-prices")
def list_market_prices(principal: CurrentPrincipal) -> dict:
    """查询市场价参考数据（PRD 3.2 财务人员维护市场价参考数据）。"""
    rows = reference_service.list_market_prices(principal.role_codes)
    return {"items": as_list(rows), "total": len(rows)}


@router.get("/audit-logs")
def list_audit_logs(principal: CurrentPrincipal, resource_type: str | None = None,
                    limit: int = 200) -> dict:
    """查询操作日志（PRD 2.7.4 审核记录页、第 13 章日志查询）。"""
    rows = reference_service.list_audit_logs(principal.role_codes, principal.user_id,
                                             resource_type, limit)
    return {"items": as_list(rows), "total": len(rows)}
