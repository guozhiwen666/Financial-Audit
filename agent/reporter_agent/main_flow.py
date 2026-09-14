"""A4 报告与留痕智能体主流程（PRD 20.2）。

职责：把风险结论渲染为报告正文与面板数据、导出 Markdown / PDF / HTML、
归档人工复核结果、触发操作审计留痕。
边界：不新增或删除风险项、不改风险等级与处理建议、不改写已提交的复核与审批记录
（留痕只可追加，不可修改或删除，PRD 20.1 P7）。
"""

import json  # 事实清单的序列化（作为报告撰写提示词的输入）
from datetime import date, datetime, timezone  # 报告生成时间与留痕时间
from decimal import Decimal  # 金额的文本化
from enum import Enum  # 枚举的文本化

from schema.enums import Recommendation, RiskLevel  # 整体风险等级与处理建议
from schema.tables_analysis import ManualReview, ReviewReport, RiskFinding  # 报告与复核记录
from schema.tables_document import FinancialDocument  # 单据实体（报告摘要的事实来源）
from schema.tables_reference import AuditLog  # 操作审计留痕

from agent.utils.llm import LLMClient  # 公共大模型调用封装（PRD 20.4 L11）
from agent.utils.message import MessagePublisher  # 公共实时消息推送（PRD 14.2）

__all__ = ["ReporterAgent"]

# PRD 13.10：导出接口支持这三种格式
EXPORT_FORMATS = ("markdown", "pdf", "html")
# PRD 第 15 章规定的报告章节
REPORT_SECTIONS = ("单据摘要", "整体风险", "金额核对", "风险项列表", "证据列表",
                   "供应商风险", "处理建议", "人工复核")
# 处理建议的取值集合由 PRD 2.7.13 / 第 15 章规定；其推导规则 PRD 未明确，
# 故此处按整体风险等级做**确定性映射**（本项目约定，未经大模型判定）：低→建议通过、
# 中→人工复核、高→建议驳回。取值「补充材料」由人工复核时按需选择。
RECOMMENDATION_BY_LEVEL = {
    RiskLevel.LOW: Recommendation.APPROVE,
    RiskLevel.MEDIUM: Recommendation.MANUAL_REVIEW,
    RiskLevel.HIGH: Recommendation.REJECT,
}


def _json_default(value):
    """JSON 序列化兜底：枚举取取值、金额与时间转字符串（与接口序列化口径一致）。"""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


class ReporterAgent:
    """A4 报告与留痕智能体。"""

    def __init__(self, llm: LLMClient, publisher: MessagePublisher) -> None:
        self.llm = llm
        self.publisher = publisher

    def run(self, task_id: int, document: FinancialDocument, findings: list[RiskFinding],
            overall_level: RiskLevel, amount_comparison: dict, reviews: list[ManualReview],
            attachment_count: int = 0, fmt: str = "markdown") -> ReviewReport:
        """主流程：载入结论 → 生成面板 → 撰写正文 → 导出报告 → 归档复核 → 写审计留痕。"""
        self.task_id = task_id
        self.document = document
        self.document_id = document.id or 0
        self.attachment_count = attachment_count
        self.step1_load_findings(findings, overall_level)
        self.risk_summary = self.step2_build_panels(amount_comparison)
        self.report = self.step3_write_report()
        self.step4_export_report(fmt)
        self.archived_reviews = self.step5_archive_review(reviews)
        self.audit_log = self.step6_write_audit_log()
        return self.report

    def step1_load_findings(self, findings: list[RiskFinding],
                            overall_level: RiskLevel) -> None:
        """载入风险项与整体等级（只读，不增删、不改写，PRD 20.2 边界、20.1 P7）。"""
        self.findings = findings
        self.overall_level = overall_level

    def step2_build_panels(self, amount_comparison: dict) -> dict:
        """生成面板数据：按风险等级与风险类型统计数量（确定性聚合，PRD 6.2.8 分类统计）。"""
        summary = {level.value: sum(1 for f in self.findings if f.risk_level is level)
                   for level in RiskLevel}
        summary["by_type"] = {
            f.risk_type: sum(1 for g in self.findings if g.risk_type == f.risk_type)
            for f in self.findings}
        self.amount_comparison = amount_comparison
        return summary

    def step3_write_report(self) -> ReviewReport:
        """【大模型 L11】按 PRD 第 15 章章节撰写正文（等级与建议沿用既有结论，不重新判定）。

        提示词只提供本次审核的**真实事实**（单据摘要、整体风险、金额核对、风险项四要素），
        并要求事实缺失处写「未提供」——禁止模型编造编号、金额、数量或供应商
        （PRD 20.1 P1 判定不由模型承担、P4 智能体只产出结论）。
        """
        # 步骤 1：组装事实清单——单据摘要取 PRD 15 列举的字段，金额核对与风险项均取既有结论
        document = self.document
        facts = {
            "单据摘要": {
                "单据类型": document.document_type, "单据编号": document.document_no,
                "申请人": document.applicant_id, "申请部门": document.applicant_department,
                "预算部门": document.budget_department, "收款单位": document.payee_name,
                "总金额": document.total_amount, "币种": document.currency,
                "申请日期": document.apply_date, "事由": document.reason_text,
                "附件数量": self.attachment_count},
            "整体风险": {"整体等级": self.overall_level,
                         "数量统计": self.risk_summary,
                         "处理建议": RECOMMENDATION_BY_LEVEL.get(self.overall_level)},
            "金额核对": self.amount_comparison,
            "风险项列表": [{"风险类型": f.risk_type, "风险等级": f.risk_level,
                            "风险标题": f.risk_title, "风险描述": f.description,
                            "实际值": f.actual_value_json, "参考值": f.reference_value_json,
                            "规则阈值": f.threshold_json, "处理建议": f.suggestion_text,
                            "复核状态": f.review_status} for f in self.findings],
        }
        # 步骤 2：要求模型只做归纳与措辞，缺失事实写「未提供」（PRD 16 结论须保留数据来源）
        body = self.llm.complete(
            "你是财务单据风险审核报告的撰写员。请**仅依据下列事实**撰写报告，逐项覆盖这些章节：%s。\n"
            "硬性要求：不得编造任何单据编号、金额、数量、供应商名称或日期；"
            "事实中缺失的内容一律写「未提供」；金额与等级直接引用事实中的取值。\n"
            "事实：%s" % ("、".join(REPORT_SECTIONS),
                          json.dumps(facts, ensure_ascii=False, default=_json_default)))
        # 步骤 3：组装报告实体（主键待落库后回填，故以 0 占位）
        return ReviewReport(id=0,
                            task_id=self.task_id, document_id=self.document_id,
                            overall_risk_level=self.overall_level,
                            risk_summary_json=self.risk_summary,
                            amount_comparison_json=self.amount_comparison,
                            recommendation=RECOMMENDATION_BY_LEVEL.get(self.overall_level),
                            report_markdown=body, created_at=datetime.now(timezone.utc))

    def step4_export_report(self, fmt: str) -> None:
        """导出报告：格式限于 PRD 13.10 允许的三类，越界即报错并允许重试；成功后推送 report_ready。"""
        self.export_format = fmt
        if fmt not in EXPORT_FORMATS:
            self.publisher.error(self.task_id, "EXPORT_FORMAT_UNSUPPORTED",
                                 "不支持的导出格式：%s" % fmt)
            return
        self.publisher.report_ready(self.task_id, self.report.id, self.overall_level.value)

    def step5_archive_review(self, reviews: list[ManualReview]) -> list[ManualReview]:
        """归档人工复核记录：只追加，不改写既有记录（PRD 2.7.14 安全边界）。"""
        return list(reviews)

    def step6_write_audit_log(self) -> AuditLog:
        """写入操作审计留痕：操作时间与变更内容；user_id 为空表示系统动作（PRD 2.7.14、3.3）。"""
        return AuditLog(id=0,  # 主键待落库后回填，故以 0 占位
                        user_id=None, action_type="report_export",
                        resource_type="review_reports", resource_id=self.report.id,
                        detail_json={"export_format": self.export_format},
                        created_at=datetime.now(timezone.utc))
