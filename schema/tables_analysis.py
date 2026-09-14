"""分析与报告表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
"""

from dataclasses import dataclass        # dataclass：声明纯字段结构
from datetime import datetime            # datetime：任务与报告时间戳
from typing import Any                   # Any：JSON 列内的值类型不固定

from schema.enums import (
    AnalysisTaskStatus,                  # 分析任务状态
    Recommendation,                      # 处理建议（四类之一）
    RiskLevel,                           # 风险等级（单项与整体）
    RiskReviewStatus,                    # 风险项复核状态
)

__all__ = [
    "AnalysisTask",     # 分析任务表
    "RiskFinding",      # 风险项表
    "ReviewReport",     # 风险报告表
    "ManualReview",     # 人工复核表
]


@dataclass
class AnalysisTask:
    """analysis_tasks 表：一次风险分析的执行实例。"""

    id: int                                                   # 主键
    session_id: int | None = None                             # 发起该分析的会话主键，指向 review_sessions.id
    document_id: int | None = None                            # 被分析的单据主键，指向 financial_documents.id
    task_status: AnalysisTaskStatus | None = None              # 任务状态（排队/解析附件/分析中/已完成等）
    current_step: str | None = None                           # 当前执行步骤，用于展示进度说明
    started_at: datetime | None = None                        # 任务开始时间
    finished_at: datetime | None = None                       # 任务结束时间（未结束时为空）
    error_message: str | None = None                          # 失败原因（成功时为空）


@dataclass
class RiskFinding:
    """risk_findings 表：单条风险结论及其判断依据。

    实际值、对比值、规则阈值、证据均由 *_json 字段承载（PRD 2.7.7 可解释性要求）。
    """

    id: int                                                     # 主键
    task_id: int | None = None                                  # 所属分析任务主键，指向 analysis_tasks.id
    risk_type: str | None = None                                # 风险类型，对应命中的风险规则
    risk_level: RiskLevel | None = None                         # 风险等级（低/中/高）
    risk_title: str | None = None                               # 风险标题，用于列表快速识别
    description: str | None = None                              # 风险描述，说明问题是什么
    actual_value_json: dict[str, Any] | None = None              # 实际计算值（如发票合计金额）
    reference_value_json: dict[str, Any] | None = None           # 对比值（如单据申请金额）
    threshold_json: dict[str, Any] | None = None                 # 触发所用规则阈值（容差等）
    evidence_json: dict[str, Any] | None = None                  # 证据来源（附件、页码、位置、置信度）
    suggestion_text: str | None = None                           # 处理建议说明
    review_status: RiskReviewStatus | None = None                # 人工复核状态（待复核/确认/否定）
    created_at: datetime | None = None                           # 风险项产出时间


@dataclass
class ReviewReport:
    """review_reports 表：风险审核报告。"""

    id: int                                                   # 主键
    task_id: int | None = None                                # 所属分析任务主键，指向 analysis_tasks.id
    document_id: int | None = None                            # 被审核单据主键，指向 financial_documents.id
    overall_risk_level: RiskLevel | None = None               # 整体风险等级（取最高单项并结合数量）
    risk_summary_json: dict[str, Any] | None = None           # 风险分类统计（各等级与各类型的数量）
    amount_comparison_json: dict[str, Any] | None = None      # 金额核对结果（五个口径及差异）
    recommendation: Recommendation | None = None              # 处理建议（建议通过/补充材料/人工复核/建议驳回）
    report_markdown: str | None = None                        # 报告正文（Markdown 形式，供展示与导出）
    created_at: datetime | None = None                        # 报告生成时间


@dataclass
class ManualReview:
    """manual_reviews 表：人工复核记录。"""

    id: int                                        # 主键
    report_id: int | None = None                   # 所属报告主键，指向 review_reports.id
    reviewer_id: int | None = None                 # 复核人用户主键，指向 users.id
    review_result: str | None = None               # 复核结论（取值 PRD 未列举，保持字符串）
    review_comment: str | None = None              # 复核意见
    reviewed_at: datetime | None = None            # 复核时间
