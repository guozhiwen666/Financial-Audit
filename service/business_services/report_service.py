"""报告模块与审核模块（PRD 11 章「报告模块」「审核模块」、13.6、13.8、第 15 章）。

职责：风险结果保存与查询、可视化面板数据生成、报告导出，以及人工复核意见与风险项处理状态记录。
边界：风险项与整体等级一律来自既有结论（A3 判定），本模块只做查询、统计与导出，不重新研判；
人工复核只追加记录、不改写既有结论（PRD 20.1 P7）。
"""

from schema.tables_analysis import ManualReview  # 人工复核记录实体
from service.infrastructure import repository as repo, runtime
from service.business_services import analysis_service, auth_service, document_service
from service.infrastructure.errors import BadRequest, NotFound, PermissionDenied

__all__ = ["get_report", "export", "amount_comparison", "update_finding_status",
           "submit_manual_review", "list_manual_reviews", "EXPORT_FORMATS"]

# 导出格式：取值严格取自 PRD 13.10（format=markdown|pdf|html）
EXPORT_FORMATS = ("markdown", "pdf", "html")


def _require_report(report_id: int, role_codes: list[str], user_id: int):
    """取报告并校验数据权限（PRD 3.3 数据权限规则）。"""
    # 步骤 1：报告必须存在
    report = repo.review_reports.get(report_id)
    if report is None:
        raise NotFound("风险报告不存在：%s" % report_id)
    # 步骤 2：按报告所属单据校验可见性
    document = document_service.require_document(report.document_id)
    if not auth_service.can_view_document(role_codes, user_id, document):
        raise PermissionDenied("无权访问该风险报告")
    return report, document


def get_report(task_id: int, role_codes: list[str], user_id: int) -> dict:
    """查询风险报告和面板数据（PRD 13.6 GET /analysis-tasks/{task_id}/report）。"""
    analysis_service.require_task(task_id, role_codes, user_id)
    # 步骤 1：取该任务下的报告；一个分析任务对应一份报告
    reports = repo.review_reports.find("task_id = %s", (task_id,), order="id DESC", limit=1)
    if not reports:
        raise NotFound("该分析任务尚未生成报告：%s" % task_id)
    report = reports[0]
    # 步骤 2：取风险项并按等级、类型统计，构成面板数据（PRD 15 整体风险与风险项列表）
    findings = repo.risk_findings.find("task_id = %s", (task_id,))
    level_counts = {"high": 0, "medium": 0, "low": 0}
    type_counts: dict[str, int] = {}
    for finding in findings:
        level_counts[(finding.risk_level.value if finding.risk_level else "low")] = \
            level_counts.get(finding.risk_level.value if finding.risk_level else "low", 0) + 1
        type_counts[finding.risk_type or "未分类"] = type_counts.get(finding.risk_type or "未分类", 0) + 1
    # 步骤 3：返回报告正文与面板数据
    return {"report": report, "findings": findings, "level_counts": level_counts,
            "type_counts": type_counts}


def export(report_id: int, fmt: str, role_codes: list[str], user_id: int) -> tuple[str, str]:
    """导出风险审核报告，返回 (内容, 内容类型)（PRD 13.6 GET /review-reports/{id}/export）。"""
    # 步骤 1：格式闸口——仅 PRD 13.10 列举的三种格式
    if fmt not in EXPORT_FORMATS:
        raise BadRequest("不支持的导出格式 %s，仅支持 %s（PRD 13.10）"
                         % (fmt, " / ".join(EXPORT_FORMATS)))
    report, document = _require_report(report_id, role_codes, user_id)
    # 步骤 2：markdown 与 html 由环节六直接产出内容（markdown 为正文、html 为渲染结果）
    if fmt in ("markdown", "html"):
        content = runtime.flow().report_export.export(report, fmt)
        media = "text/markdown; charset=utf-8" if fmt == "markdown" else "text/html; charset=utf-8"
        return content, media
    # 步骤 3：pdf 需渲染库；未安装时明确报错并给出替代方案，不静默返回错误格式的内容
    return _to_pdf(report)


def _to_pdf(report) -> tuple[str, str]:
    """用 reportlab 渲染 PDF；未安装该库时给出明确的安装提示（PRD 13.10 支持 pdf 导出）。"""
    # 步骤 1：渲染库缺失时显式报错——静默降级会让调用方拿到不是 PDF 的产物
    try:
        from reportlab.lib.pagesizes import A4  # noqa: PLC0415
        from reportlab.lib.styles import ParagraphStyle  # noqa: PLC0415
        from reportlab.pdfbase import pdfmetrics  # noqa: PLC0415
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont  # noqa: PLC0415
        from reportlab.platypus import Paragraph, SimpleDocTemplate  # noqa: PLC0415
    except ImportError as exc:
        raise BadRequest(
            "PDF 导出需要 reportlab（已声明于 pyproject.toml，尚未安装）。"
            "可先使用 format=html 并在浏览器中打印为 PDF。原始错误：%s" % exc) from exc
    # 步骤 2：注册中文字体（reportlab 内置 CID 字体），否则中文正文无法渲染
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    style = ParagraphStyle("report", fontName="STSong-Light", fontSize=10, leading=16)
    # 步骤 3：渲染到项目内的导出目录
    from pathlib import Path  # noqa: PLC0415
    target_dir = Path("exports")
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / ("report_%s.pdf" % report.id)
    document = SimpleDocTemplate(str(target), pagesize=A4)
    body = (report.report_markdown or "").replace("<", "&lt;").replace(">", "&gt;")
    document.build([Paragraph(line or " ", style) for line in body.splitlines()])
    return str(target), "application/pdf"


def amount_comparison(document_id: int, role_codes: list[str], user_id: int) -> dict:
    """查询金额核对结果（PRD 13.6 GET /documents/{document_id}/amount-comparison）。"""
    # 步骤 1：取单据并校验数据权限
    document = document_service.require_document(document_id)
    if not auth_service.can_view_document(role_codes, user_id, document):
        raise PermissionDenied("无权访问该单据")
    # 步骤 2：取明细、附件与其名下发票，作为核对口径的输入
    line_items = repo.document_line_items.find("document_id = %s", (document_id,), order="id")
    attachments = repo.document_attachments.find("document_id = %s", (document_id,), order="id")
    attachment_ids = [a.id for a in attachments if a.id]
    invoices = []
    if attachment_ids:
        placeholders = ", ".join(["%s"] * len(attachment_ids))
        invoices = repo.invoice_records.find("attachment_id IN (%s)" % placeholders,
                                             attachment_ids, order="id")
    # 步骤 3：合同金额取自合同附件的解析结果；无解析结果时为 None，不臆造
    parse_results = []
    if attachment_ids:
        placeholders = ", ".join(["%s"] * len(attachment_ids))
        parse_results = repo.attachment_parse_results.find(
            "attachment_id IN (%s)" % placeholders, attachment_ids, order="id")
    contract_amount = runtime.flow().contract_amount_from(parse_results)
    # 步骤 4：交环节四做确定性对照计算（差异与偏离比例，PRD 9.3）
    return runtime.flow().risk_analysis.compare_amounts(document, line_items, invoices,
                                                        contract_amount)


def update_finding_status(finding_id: int, status: str, role_codes: list[str], user_id: int):
    """更新风险项人工复核状态（PRD 13.8 PATCH /risk-findings/{finding_id}/review-status）。"""
    # 步骤 1：仅审批人员可填写复核意见（PRD 3.2）
    if not auth_service.can_review(role_codes):
        raise PermissionDenied("仅审批人员可更新风险项复核状态（PRD 3.2）")
    # 步骤 2：风险项必须存在，且状态取值须在 PRD 2.7.12 列举范围内
    finding = repo.risk_findings.get(finding_id)
    if finding is None:
        raise NotFound("风险项不存在：%s" % finding_id)
    review_status = repo.risk_findings.coerce("review_status", status)
    # 步骤 3：交环节五处理——回写状态并写审计留痕（PRD 2.7.14 风险项处理必须留痕）
    runtime.flow().manual_review.review_finding(finding, review_status)
    repo.risk_findings.update(finding_id, review_status=finding.review_status)
    runtime.flush_audit_logs()
    return finding


def list_manual_reviews(report_id: int, role_codes: list[str], user_id: int) -> list:
    """查询报告下的人工复核记录（PRD 15 人工复核）。"""
    _require_report(report_id, role_codes, user_id)
    return repo.manual_reviews.find("report_id = %s", (report_id,), order="reviewed_at")


def submit_manual_review(report_id: int, payload: dict, role_codes: list[str],
                         user_id: int) -> ManualReview:
    """提交人工复核意见和审批结果（PRD 13.8 POST /review-reports/{id}/manual-reviews）。"""
    # 步骤 1：仅审批人员可提交复核意见（PRD 3.2）
    if not auth_service.can_review(role_codes):
        raise PermissionDenied("仅审批人员可提交复核意见（PRD 3.2）")
    _require_report(report_id, role_codes, user_id)
    # 步骤 2：复核结论必填；review_result 的取值 PRD 未列举，故按原样接收
    if not payload.get("review_result"):
        raise BadRequest("缺少必填字段 review_result（PRD 15 人工复核）")
    # 步骤 3：交环节五构造复核记录并写审计留痕（只追加，PRD 20.1 P7）
    record = runtime.flow().manual_review.submit_conclusion(
        report_id, user_id, payload["review_result"], payload.get("review_comment"))
    # 步骤 4：落库并回填主键
    record.id = repo.manual_reviews.insert(record)
    runtime.flush_audit_logs()
    return record
