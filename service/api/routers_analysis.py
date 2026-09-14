"""分析、报告与复核接口（PRD 13.6、13.8）。

覆盖：创建分析任务、查询任务状态、查询风险项、查询报告与面板数据、金额核对、报告导出、
更新风险项复核状态、提交人工复核意见。
所有风险结论均来自主流程（LangGraph）中 A3 的确定性判定与表述（PRD 20.1 P1）。
"""

from typing import Annotated

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import Response  # 导出内容响应

from service.infrastructure import idempotency
from service.business_services import analysis_service, report_service
from service.api.deps import CurrentPrincipal
from service.api.serializers import as_dict, as_list

__all__ = ["router"]

router = APIRouter(tags=["分析与报告"])


@router.post("/documents/{document_id}/analysis")
def create_analysis(document_id: int, principal: CurrentPrincipal,
                    idempotency_key: Annotated[str, Header()] = "") -> dict:
    """创建单据风险分析任务（PRD 13.6 POST /documents/{document_id}/analysis）。"""
    # 步骤 1：按幂等键执行，重复请求不产生重复分析任务与重复报表（PRD 11.1）
    state = idempotency.run_once(
        idempotency_key, "analysis:%s" % document_id,
        lambda: analysis_service.create_analysis(document_id, principal.role_codes,
                                                 principal.user_id))
    # 步骤 2：返回分析任务、风险项、整体等级与报告
    return {"analysis_task": as_dict(state.get("analysis_task")),
            "findings": as_list(state.get("findings") or []),
            "overall_level": as_dict(state.get("overall_level")),
            "amount_comparison": as_dict(state.get("amount_comparison") or {}),
            "report": as_dict(state.get("report"))}


@router.get("/analysis-tasks/{task_id}")
def get_analysis_task(task_id: int, principal: CurrentPrincipal) -> dict:
    """查询分析任务状态和当前步骤（PRD 13.6 GET /analysis-tasks/{task_id}）。"""
    result = analysis_service.get_task(task_id, principal.role_codes, principal.user_id)
    return {"task": as_dict(result["task"]), "progress": result["progress"]}


@router.get("/analysis-tasks/{task_id}/findings")
def list_findings(task_id: int, principal: CurrentPrincipal) -> dict:
    """查询风险项列表（PRD 13.6 GET /analysis-tasks/{task_id}/findings）。"""
    findings = analysis_service.get_findings(task_id, principal.role_codes, principal.user_id)
    return {"items": as_list(findings), "total": len(findings)}


@router.get("/analysis-tasks/{task_id}/report")
def get_report(task_id: int, principal: CurrentPrincipal) -> dict:
    """查询风险报告和面板数据（PRD 13.6 GET /analysis-tasks/{task_id}/report）。"""
    result = report_service.get_report(task_id, principal.role_codes, principal.user_id)
    return {"report": as_dict(result["report"]), "findings": as_list(result["findings"]),
            "level_counts": result["level_counts"], "type_counts": result["type_counts"]}


@router.get("/documents/{document_id}/amount-comparison")
def amount_comparison(document_id: int, principal: CurrentPrincipal) -> dict:
    """查询金额核对结果（PRD 13.6 GET /documents/{document_id}/amount-comparison）。"""
    return report_service.amount_comparison(document_id, principal.role_codes, principal.user_id)


@router.get("/review-reports/{report_id}/export")
def export_report(report_id: int, principal: CurrentPrincipal,
                  format: str = Query(default="markdown")) -> Response:
    """导出风险审核报告（PRD 13.6 GET /review-reports/{report_id}/export、13.10 三种格式）。"""
    # 步骤 1：按 PRD 13.10 的 format 参数导出，越界格式由服务层拒绝
    content, media_type = report_service.export(report_id, format, principal.role_codes,
                                                principal.user_id)
    # 步骤 2：PDF 导出产出的是文件路径，故以文件方式返回；文本格式直接返回内容
    if media_type == "application/pdf":
        from pathlib import Path  # noqa: PLC0415
        return Response(content=Path(content).read_bytes(), media_type=media_type,
                        headers={"Content-Disposition": "attachment; filename=report_%s.pdf"
                                                        % report_id})
    return Response(content=content, media_type=media_type)


@router.patch("/risk-findings/{finding_id}/review-status")
def update_finding_status(finding_id: int, payload: Annotated[dict, Body()],
                          principal: CurrentPrincipal) -> dict:
    """更新风险项人工复核状态（PRD 13.8 PATCH /risk-findings/{finding_id}/review-status）。"""
    finding = report_service.update_finding_status(finding_id, payload.get("review_status") or "",
                                                   principal.role_codes, principal.user_id)
    return {"finding": as_dict(finding)}


@router.post("/review-reports/{report_id}/manual-reviews")
def submit_manual_review(report_id: int, payload: Annotated[dict, Body()],
                         principal: CurrentPrincipal) -> dict:
    """提交人工复核意见和审批结果（PRD 13.8 POST /review-reports/{id}/manual-reviews）。"""
    record = report_service.submit_manual_review(report_id, payload, principal.role_codes,
                                                 principal.user_id)
    return {"manual_review": as_dict(record)}


@router.get("/review-reports/{report_id}/manual-reviews")
def list_manual_reviews(report_id: int, principal: CurrentPrincipal) -> dict:
    """查询报告下的人工复核记录（PRD 15 人工复核）。"""
    records = report_service.list_manual_reviews(report_id, principal.role_codes,
                                                 principal.user_id)
    return {"items": as_list(records), "total": len(records)}
