"""A4 报告与留痕智能体主流程（PRD 20.2）。

职责：把风险结论渲染为报告正文与面板数据、导出 Markdown / PDF / HTML、
归档人工复核结果、触发操作审计留痕。
边界：不新增或删除风险项、不改风险等级与处理建议、不改写已提交的复核与审批记录
（留痕只可追加，不可修改或删除，PRD 20.1 P7）。
"""

from datetime import datetime, timezone  # 报告生成时间与留痕时间

from schema.enums import RiskLevel  # 整体风险等级
from schema.tables_analysis import ManualReview, ReviewReport, RiskFinding  # 报告与复核记录
from schema.tables_reference import AuditLog  # 操作审计留痕

from agent.utils.llm import LLMClient  # 公共大模型调用封装（PRD 20.4 L11）
from agent.utils.message import MessagePublisher  # 公共实时消息推送（PRD 14.2）

__all__ = ["ReporterAgent"]

# PRD 13.10：导出接口支持这三种格式
EXPORT_FORMATS = ("markdown", "pdf", "html")
# PRD 第 15 章规定的报告章节
REPORT_SECTIONS = ("单据摘要", "整体风险", "金额核对", "风险项列表", "证据列表",
                   "供应商风险", "处理建议", "人工复核")


class ReporterAgent:
    """A4 报告与留痕智能体。"""

    def __init__(self, llm: LLMClient, publisher: MessagePublisher) -> None:
        self.llm = llm
        self.publisher = publisher

    def run(self, task_id: int, document_id: int, findings: list[RiskFinding],
            overall_level: RiskLevel, amount_comparison: dict, reviews: list[ManualReview],
            fmt: str = "markdown") -> ReviewReport:
        """主流程：载入结论 → 生成面板 → 撰写正文 → 导出报告 → 归档复核 → 写审计留痕。"""
        self.task_id = task_id
        self.document_id = document_id
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
        summary["by_type"] = {f.risk_type: sum(1 for g in self.findings if g.risk_type == f.risk_type)
                              for f in self.findings}
        self.amount_comparison = amount_comparison
        return summary

    def step3_write_report(self) -> ReviewReport:
        """【大模型 L11】按 PRD 第 15 章章节撰写正文，并组装报告（等级与建议沿用既有结论）。"""
        body = self.llm.complete(
            "按以下章节撰写财务单据风险审核报告：%s。\n整体风险等级：%s\n风险项：%s"
            % ("、".join(REPORT_SECTIONS), self.overall_level.value,
               [f.risk_title for f in self.findings]))
        return ReviewReport(id=0,  # 主键待落库后回填，故以 0 占位（schema 约定主键必填）
                            task_id=self.task_id, document_id=self.document_id,
                            overall_risk_level=self.overall_level,
                            risk_summary_json=self.risk_summary,
                            amount_comparison_json=self.amount_comparison,
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
