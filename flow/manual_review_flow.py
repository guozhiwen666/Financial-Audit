"""环节五 人工复核（PRD 2.7.1 人工复核、13.8、2.7.14）。

职责：更新风险项的人工复核状态（待复核 / 已确认 / 已否定）、提交人工复核意见与审批结果。
本环节对应后端「审核模块」（PRD 2.7.9）。

边界（PRD 20.1 P7）：复核记录与留痕只可追加，不得改写已提交的复核与审批记录；
风险项处理的「操作人」与「时间」在 ``risk_findings`` 表中无对应列，故一并记入操作审计留痕
（PRD 2.7.14 要求风险项处理必须记录操作人、操作时间与变更内容）。
"""

from datetime import datetime, timezone  # 复核时间与留痕时间（PRD 12.2：时间戳统一 UTC）

from flow.audit_log_flow import AuditLogFlow  # 环节七 操作审计：本环节写复核操作留痕
from schema.enums import RiskReviewStatus  # 风险项复核状态（待复核 / 已确认 / 已否定）
from schema.tables_analysis import ManualReview, RiskFinding  # 人工复核记录、风险项

__all__ = ["ManualReviewFlow"]


class ManualReviewFlow:
    """环节五 人工复核（PRD 2.7.1、6.2.8）。"""

    def __init__(self, audit_log: AuditLogFlow) -> None:
        """注入审计环节。"""
        self.audit_log = audit_log  # 风险项处理留痕（PRD 2.7.14）

    def review_finding(self, finding: RiskFinding, review_status: RiskReviewStatus) -> RiskFinding:
        """更新风险项的人工复核状态：待复核 / 已确认 / 已否定（PRD 13.8 更新风险项复核状态）。"""
        # 步骤 1：回写复核状态到风险项实体
        finding.review_status = review_status
        # 步骤 2：写审计留痕——risk_findings 表无操作人与时间列，故操作人与变更内容记入留痕（2.7.14）
        self.audit_log.record("review_risk_finding", "risk_findings", finding.id,
                              detail={"review_status": review_status.value})
        # 步骤 3：返回复核后的风险项实体，供调用方落库
        return finding

    def submit_conclusion(self, report_id: int, reviewer_id: int, review_result: str,
                          review_comment: str | None = None) -> ManualReview:
        """提交人工复核意见与审批结果：追加复核记录并写审计留痕（PRD 13.8、2.7.14）。"""
        # 步骤 1：构造复核记录——主键待落库后回填故以 0 占位；复核时间取当前 UTC
        record = ManualReview(id=0,
                              report_id=report_id,              # 所属风险报告
                              reviewer_id=reviewer_id,          # 复核人，指向 users.id
                              review_result=review_result,      # 复核结论（取值 PRD 未列举）
                              review_comment=review_comment,    # 复核意见
                              reviewed_at=datetime.now(timezone.utc))
        # 步骤 2：写审计留痕——记录操作人（复核人）与复核结论（PRD 2.7.14）
        #         只追加新记录，不改写既有复核（PRD 20.1 P7）
        self.audit_log.record("submit_manual_review", "manual_reviews", record.id, reviewer_id,
                              {"review_result": review_result})
        # 步骤 3：返回复核记录，供调用方落库
        return record
