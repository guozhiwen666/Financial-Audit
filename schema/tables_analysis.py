"""分析与报告表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from schema.enums import AnalysisTaskStatus, Recommendation, RiskLevel, RiskReviewStatus

__all__ = ["AnalysisTask", "RiskFinding", "ReviewReport", "ManualReview"]


@dataclass
class AnalysisTask:
    """analysis_tasks 表：一次风险分析的执行实例。"""

    id: int
    session_id: int | None = None
    document_id: int | None = None
    task_status: AnalysisTaskStatus | None = None
    current_step: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None


@dataclass
class RiskFinding:
    """risk_findings 表：单条风险结论及其判断依据。

    实际值、对比值、规则阈值、证据均由 *_json 字段承载（PRD 2.7.7 可解释性要求）。
    """

    id: int
    task_id: int | None = None
    risk_type: str | None = None
    risk_level: RiskLevel | None = None
    risk_title: str | None = None
    description: str | None = None
    actual_value_json: dict[str, Any] | None = None
    reference_value_json: dict[str, Any] | None = None
    threshold_json: dict[str, Any] | None = None
    evidence_json: dict[str, Any] | None = None
    suggestion_text: str | None = None
    review_status: RiskReviewStatus | None = None
    created_at: datetime | None = None


@dataclass
class ReviewReport:
    """review_reports 表：风险审核报告。"""

    id: int
    task_id: int | None = None
    document_id: int | None = None
    overall_risk_level: RiskLevel | None = None
    risk_summary_json: dict[str, Any] | None = None
    amount_comparison_json: dict[str, Any] | None = None
    recommendation: Recommendation | None = None
    report_markdown: str | None = None
    created_at: datetime | None = None


@dataclass
class ManualReview:
    """manual_reviews 表：人工复核记录。"""

    id: int
    report_id: int | None = None
    reviewer_id: int | None = None
    review_result: str | None = None
    review_comment: str | None = None
    reviewed_at: datetime | None = None
