"""A3 风险研判智能体主流程（PRD 20.2）。

职责：聚合单据字段、明细、附件解析结果、审核规则、市场价参考数据与供应商资料；
读取规则引擎执行结果，产出风险项、等级与处理建议；按 PRD 9.2 判定表计算整体风险等级。
边界：不修改规则与阈值、不自行计算金额与差异、不决定审批结果、不越权读取（PRD 20.2）。
"""

from datetime import datetime, timezone  # 风险项产出时间

from schema.enums import RiskLevel, RiskReviewStatus  # 单项等级、复核状态
from schema.tables_analysis import RiskFinding  # 风险项（输出）
from schema.tables_document import AttachmentParseResult, DocumentLineItem, FinancialDocument

from agent.utils.llm import LLMClient  # 公共大模型调用封装（PRD 20.4 L8~L10）
from agent.utils.message import MessagePublisher  # 公共实时消息推送（PRD 14.2）

__all__ = ["RiskAnalystAgent"]

# PRD 9.2 判定表的数量阈值
MANY_MEDIUM = 3  # 无 high 但达到该数量的 medium，整体升为 high
MANY_LOW = 3     # 无 high、无 medium 但达到该数量的 low，整体升为 medium


class RiskAnalystAgent:
    """A3 风险研判智能体。"""

    def __init__(self, llm: LLMClient, publisher: MessagePublisher) -> None:
        self.llm = llm
        self.publisher = publisher

    def run(self, task_id: int, document: FinancialDocument, line_items: list[DocumentLineItem],
            parse_results: list[AttachmentParseResult],
            rule_results: list[dict]) -> tuple[list[RiskFinding], RiskLevel]:
        """主流程：接收单据 → 接收解析结果 → 接收规则结果 → 生成风险项 → 生成描述 → 算整体等级。"""
        self.task_id = task_id
        self.step1_load_document(document, line_items)
        self.step2_load_parse_results(parse_results)
        self.step3_run_rules(rule_results)
        self.findings = self.step4_build_findings()
        self.step5_describe_findings()
        return self.findings, self.step6_grade_overall()

    def step1_load_document(self, document: FinancialDocument,
                            line_items: list[DocumentLineItem]) -> None:
        """接收单据与明细；金额与合计一律取自规则引擎结果，本智能体不自行计算（PRD 20.2 边界）。"""
        self.document = document
        self.line_items = line_items

    def step2_load_parse_results(self, parse_results: list[AttachmentParseResult]) -> None:
        """接收附件解析结果；字段与证据位置由 A2 提供，本步只做持有（PRD 12.3 G10）。"""
        self.parse_results = parse_results

    def step3_run_rules(self, rule_results: list[dict]) -> None:
        """接收规则引擎（PRD 2.7.9）的执行结果：命中规则、差异值与阈值；本步不执行规则计算。"""
        self.rule_results = rule_results

    def step4_build_findings(self) -> list[RiskFinding]:
        """生成风险项：实际值、对比值、规则阈值与证据缺一不可（PRD 9.3 可解释性要求）。"""
        created_at = datetime.now(timezone.utc)
        return [RiskFinding(id=0,  # 主键待落库后回填，故以 0 占位（schema 约定主键必填）
                            task_id=self.task_id,
                            risk_type=result["risk_type"], risk_level=result["risk_level"],
                            risk_title=result["risk_title"],
                            actual_value_json=result.get("actual_value_json"),
                            reference_value_json=result.get("reference_value_json"),
                            threshold_json=result.get("threshold_json"),
                            evidence_json=result.get("evidence_json"),
                            review_status=RiskReviewStatus.PENDING, created_at=created_at)
                for result in self.rule_results]

    def step5_describe_findings(self) -> None:
        """【大模型 L9、L10】撰写风险描述、业务归因与建议措辞，并逐条推送 risk_finding（PRD 20.3）。"""
        for finding in self.findings:
            written = self.llm.extract(
                "根据风险项写出风险描述与处理建议，输出 JSON "
                '{"description":..., "suggestion_text":...}：' + finding.risk_title)
            finding.description = written.get("description")
            finding.suggestion_text = written.get("suggestion_text")
            self.publisher.risk_finding(self.task_id, finding.id, finding.risk_type,
                                        finding.risk_level.value, finding.risk_title)

    def step6_grade_overall(self) -> RiskLevel:
        """按 PRD 9.2 判定表由单项等级与风险数量计算整体等级（自上而下，命中即止）。"""
        levels = [finding.risk_level for finding in self.findings]
        high = levels.count(RiskLevel.HIGH)
        medium = levels.count(RiskLevel.MEDIUM)
        low = levels.count(RiskLevel.LOW)
        if high >= 1 or medium >= MANY_MEDIUM:
            return RiskLevel.HIGH
        if medium >= 1 or low >= MANY_LOW:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
