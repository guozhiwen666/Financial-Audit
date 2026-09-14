"""环节六 报告导出（PRD 2.7.1 报告导出、第 15 章、13.10）。

职责：把风险结论交由 **A4 报告与留痕智能体** 渲染为报告正文与面板数据，并按 PRD 13.10 支持的
格式导出报告。

边界（PRD 20.2 A4）：不新增或删除风险项、不改风险等级与处理建议；PDF / HTML 的实际渲染由后端
报告模块完成（PRD 11 章），本环节只做格式校验与内容取出。
"""

from agent.reporter_agent.main_flow import EXPORT_FORMATS, ReporterAgent  # A4 及其公开的格式白名单
from schema.enums import RiskLevel  # 整体风险等级
from schema.tables_analysis import ManualReview, ReviewReport, RiskFinding  # 报告与复核记录

__all__ = ["ReportExportFlow"]


class ReportExportFlow:
    """环节六 报告导出（PRD 2.7.1、第 15 章）。"""

    def __init__(self, reporter: ReporterAgent) -> None:
        """注入下游报告智能体。"""
        self.reporter = reporter  # 报告正文与面板数据交由 A4 报告与留痕智能体（PRD 20.2）

    def generate(self, task_id: int, document_id: int, findings: list[RiskFinding],
                 overall_level: RiskLevel, amount_comparison: dict,
                 reviews: list[ManualReview]) -> ReviewReport:
        """生成风险审核报告：交由 A4 撰写正文、聚合面板并推送 report_ready（PRD 第 15 章）。"""
        # 步骤 1：整体等级与金额核对数据均来自既有结论，本环节只做转交，不重新判定（PRD 20.2 A4）
        # 步骤 2：A4 内部按第 15 章的八个章节撰写正文，并在成功导出后推送 report_ready 消息
        return self.reporter.run(task_id, document_id, findings, overall_level,
                                 amount_comparison, reviews)

    def export(self, report: ReviewReport, fmt: str) -> str:
        """按 PRD 13.10 支持的 markdown / pdf / html 导出报告，返回导出内容。"""
        # 步骤 1：格式闸口——PRD 13.10 仅支持这三种格式，越界即报错并允许调用方重试
        if fmt not in EXPORT_FORMATS:
            raise ValueError("不支持的导出格式 %s，仅支持 %s（PRD 13.10）"
                             % (fmt, " / ".join(EXPORT_FORMATS)))
        # 步骤 2：取出报告正文作为导出内容；正文为空时返回空串而非 None，避免调用方误判
        return report.report_markdown or ""
