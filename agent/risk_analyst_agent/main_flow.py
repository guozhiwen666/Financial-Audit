"""A3 风险研判智能体主流程（PRD 20.2）。

职责：聚合单据字段、明细、附件解析结果、审核规则、市场价参考数据与供应商资料；
读取规则引擎执行结果，产出风险项、等级与处理建议；按 PRD 9.2 判定表计算整体风险等级。
边界：不修改规则与阈值、不自行计算金额与差异、不决定审批结果、不越权读取（PRD 20.2）。
"""

from agent.utils.llm import LLMClient  # 公共大模型调用封装（PRD 20.4 L8~L10）
from agent.utils.message import MessagePublisher  # 公共实时消息推送（PRD 14.2）

__all__ = ["RiskAnalystAgent"]


class RiskAnalystAgent:
    """A3 风险研判智能体。"""

    def __init__(self) -> None:
        pass

    def run(self, task_id: int, document_id: int) -> None:
        """主流程：载入单据 → 载入解析结果 → 执行规则 → 生成风险项 → 生成描述 → 计算整体等级。"""
        self.step1_load_document(document_id)
        self.step2_load_parse_results(document_id)
        self.step3_run_rules()
        self.step4_build_findings()
        self.step5_describe_findings()
        self.step6_grade_overall()

    def step1_load_document(self, document_id: int) -> None:
        """载入单据字段与明细（含数据权限过滤），并记录数据来源（PRD 2.7.1 分析能力）。"""
        pass

    def step2_load_parse_results(self, document_id: int) -> None:
        """载入附件解析结果、发票记录、市场价参考数据与供应商档案（R06、R08 的数据来源）。"""
        pass

    def step3_run_rules(self) -> None:
        """调用规则引擎执行 R01~R10 并取得命中结果；差异与阈值判定为确定性逻辑，不交大模型。"""
        pass

    def step4_build_findings(self) -> None:
        """生成风险项：填写实际值、对比值、规则阈值与证据，缺一不得落库（PRD 9.3 可解释性要求）。"""
        pass

    def step5_describe_findings(self) -> None:
        """【大模型 L9、L10】撰写风险描述与业务归因、处理建议表述（等级与建议类别由确定性逻辑确定）。"""
        pass

    def step6_grade_overall(self) -> None:
        """按 PRD 9.2 判定表由单项等级与风险数量计算整体风险等级（确定性逻辑，禁止交给大模型）。"""
        pass
