"""A1 会话编排智能体主流程（PRD 20.2）。

职责：与用户多轮交互、识别意图、抽取并确认槽位（单据类型、单据编号）、调度 A2/A3/A4、
汇总分析结果回复用户、推送进度消息。
边界：不解析附件、不产出风险结论、不修改单据字段、不绕过权限校验（PRD 20.2）。
本智能体是唯一面向用户的出口（PRD 20.1 P3）。
"""

from datetime import datetime, timezone  # done 消息的完成时间（PRD 14.2）

from schema.enums import AnalysisTaskStatus, DocumentType  # 任务进度状态、单据类型候选值
from schema.tables_analysis import ReviewReport  # 汇总回复所依据的风险报告
from schema.tables_document import FinancialDocument  # 被查询的单据
from schema.tables_session import ReviewSession  # 会话主体

from agent.utils.llm import LLMClient  # 公共大模型调用封装（PRD 20.4 L1~L4）
from agent.utils.message import MessagePublisher  # 公共实时消息推送（PRD 14.2）

__all__ = ["OrchestratorAgent"]


class OrchestratorAgent:
    """A1 会话编排智能体。"""

    def __init__(self, llm: LLMClient, publisher: MessagePublisher) -> None:
        # 公共依赖由调用方注入（大模型调用与消息推送）
        self.llm = llm
        self.publisher = publisher
        # 会话态：本次交互的槽位与查询结果
        self.slots: dict[str, str | None] = {}
        self.document: FinancialDocument | None = None
        self.summary = ""

    def run(self, session: ReviewSession, user_message: str, document: FinancialDocument | None,
            has_permission: bool, task_id: int, report: ReviewReport) -> None:
        """主流程：载入会话 → 抽取槽位 → 补问槽位 → 查询单据 → 请求派发 → 汇总回复。"""
        self.step1_load_session(session)
        self.step2_extract_slots(user_message)
        self.step3_ask_missing_slot()
        self.step4_query_document(document, has_permission)
        if self.document is None:
            return  # 单据查询失败或无数据权限时不再向下派发（PRD 8.2）
        self.step5_dispatch_agents(task_id)
        self.step6_summarize(task_id, report)

    def step1_load_session(self, session: ReviewSession) -> None:
        """载入会话主体与已确认槽位；已确认的信息不得重复询问（PRD 8.1 第 4 条）。"""
        self.session = session
        self.slots = {"document_type": session.document_type, "document_no": session.document_no}

    def step2_extract_slots(self, user_message: str) -> None:
        """【大模型 L1】识别用户意图并抽取单据类型与单据编号；已确认的槽位不被覆盖（PRD 8.1）。"""
        extracted = self.llm.extract("从用户输入中抽取单据类型与单据编号，输出 JSON "
                                     '{"document_type":..., "document_no":...}：' + user_message)
        for name in ("document_type", "document_no"):
            if not self.slots.get(name):
                self.slots[name] = extracted.get(name)

    def step3_ask_missing_slot(self) -> None:
        """【大模型 L2、L3】槽位缺失即追问；单据类型候选值取自五类单据（PRD 8.1 第 1~3 条）。"""
        if not self.slots.get("document_type"):
            self.publisher.slot_required(self.session.id, "document_type", "请问这是哪一类单据？",
                                         [t.value for t in DocumentType])
        elif not self.slots.get("document_no"):
            self.publisher.slot_required(self.session.id, "document_no", "请提供单据编号", [])

    def step4_query_document(self, document: FinancialDocument | None,
                             has_permission: bool) -> None:
        """校验单据存在与数据权限（PRD 8.1 第 6、9 条）；两者均属确定性判定，不交大模型。"""
        if document is not None and has_permission:
            self.document = document
            return
        code = "DOCUMENT_NOT_FOUND" if document is None else "PERMISSION_DENIED"
        message = "未查询到该单据，请核对单据编号后重试" if document is None else "无该单据的数据权限"
        # PRD 14.2 的 error 消息只定义 task_id；分析任务创建前的失败尚无任务号，以 0 占位
        self.publisher.error(0, code, message)

    def step5_dispatch_agents(self, task_id: int) -> None:
        """请求派发下游并推送进度；实际调用按 PRD 20.3 由确定性核心创建任务后执行。"""
        self.publisher.task_status(task_id, AnalysisTaskStatus.QUEUED.value,
                                   AnalysisTaskStatus.QUEUED.value, 0)

    def step6_summarize(self, task_id: int, report: ReviewReport) -> None:
        """【大模型 L4】把风险结论汇总为自然语言回复用户，并推送 done（PRD 8.1、14.2）。"""
        self.summary = self.llm.complete("请用中文简要汇总以下风险审核结论：\n" + (report.report_markdown or ""))
        self.publisher.done(task_id, datetime.now(timezone.utc))
