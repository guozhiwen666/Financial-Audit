"""A1 会话编排智能体主流程（PRD 20.2）。

职责：与用户多轮交互、识别意图、抽取并确认槽位（单据类型、单据编号）、调度 A2/A3/A4、
汇总分析结果回复用户、推送进度消息。
边界：不解析附件、不产出风险结论、不修改单据字段、不绕过权限校验（PRD 20.2）。
本智能体是唯一面向用户的出口（PRD 20.1 P3）。
"""

from agent.utils.llm import LLMClient  # 公共大模型调用封装（PRD 20.4 L1~L4）
from agent.utils.message import MessagePublisher  # 公共实时消息推送（PRD 14.2）

__all__ = ["OrchestratorAgent"]


class OrchestratorAgent:
    """A1 会话编排智能体。"""

    def __init__(self) -> None:
        pass

    def run(self, session_id: int, user_message: str) -> None:
        """主流程：载入会话 → 抽取槽位 → 补问槽位 → 查询单据 → 派发下游 → 汇总回复。"""
        self.step1_load_session(session_id)
        self.step2_extract_slots(user_message)
        self.step3_ask_missing_slot()
        self.step4_query_document()
        self.step5_dispatch_agents()
        self.step6_summarize()

    def step1_load_session(self, session_id: int) -> None:
        """载入会话主体与已确认槽位（session_slots）；已确认信息不得重复询问（PRD 8.1 第 4 条）。"""
        pass

    def step2_extract_slots(self, user_message: str) -> None:
        """【大模型 L1】识别用户意图，从自然语言中抽取单据类型与单据编号槽位（PRD 20.4 L1）。"""
        pass

    def step3_ask_missing_slot(self) -> None:
        """【大模型 L2、L3】槽位缺失时推送 slot_required 追问；存在歧义时展示候选项请用户确认。"""
        pass

    def step4_query_document(self) -> None:
        """按「单据类型 + 单据编号」查询单据，并校验登录状态与数据权限（确定性逻辑，PRD 20.1 P1）。"""
        pass

    def step5_dispatch_agents(self) -> None:
        """派发下游：A2 凭证解析 → A3 风险研判 → A4 报告留痕，同步推送 task_status 进度。"""
        pass

    def step6_summarize(self) -> None:
        """【大模型 L4】将风险结论汇总为自然语言回复用户；失败时推送 error 展示失败环节（PRD 8.1）。"""
        pass
