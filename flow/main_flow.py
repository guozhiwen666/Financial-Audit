"""最外层主流程（PRD 2.7.1 / 第 7 章 / 第 8 章 / 第 20 章）——以 LangGraph 编排。

PRD 2.7.1 定义本系统覆盖七个环节：单据创建、附件管理、审批流转、风险分析、人工复核、报告导出、
操作审计。本模块只保留**装配与驱动**：把七个环节与四个智能体装配成 LangGraph 图并按序驱动，
各环节的职责分别落在同目录下的 ``*_flow.py``：

* 环节一 ``document_creation_flow.py``   * 环节二 ``attachment_flow.py``
* 环节三 ``approval_flow.py``            * 环节四 ``risk_analysis_flow.py``
* 环节五 ``manual_review_flow.py``       * 环节六 ``report_export_flow.py``
* 环节七 ``audit_log_flow.py``           * 流转表 ``status_transitions.py``

两张图（均为 LangGraph ``StateGraph``，状态用 ``dict`` 承载，不新增数据结构）：

1. ``workflow_graph``（PRD 7.1）——单据提交链路：提交 → 解析 → 规则 → 研判 → 核对 → 报告 → 留痕；
2. ``intake_graph``（PRD 8.1）——多轮交互链路：A1 编排 → （需澄清则结束等待补充）→ 同上分析段。

本项目为多智能体协同：本层只做编排，**不承担任何业务规则**。金额合计与差异、规则命中、风险等级
取值、状态流转、权限校验一律由对应环节或规则引擎确定性实现（PRD 20.1 P1）；大模型只在 A2 / A3 / A4
内部使用，智能体只产出结论（PRD 20.1 P4）。审批与复核由人工触发，不在自动段内
（PRD 2.7.14 要求最终审批结果由有权限的人员人工确认）。
"""

from decimal import Decimal  # 合同金额文本的转换

from langgraph.graph import END, START, StateGraph  # 主流程装配（PRD 7.1、8.1）

from agent.document_parser_agent.main_flow import DocumentParserAgent  # A2 凭证解析
from agent.orchestrator_agent.main_flow import OrchestratorAgent  # A1 会话编排
from agent.reporter_agent.main_flow import ReporterAgent  # A4 报告留痕
from agent.risk_analyst_agent.main_flow import RiskAnalystAgent  # A3 风险研判
from agent.utils.llm import LLMClient  # 大模型调用：由本层创建后注入各智能体（PRD 20.4）
from agent.utils.message import MessagePublisher  # 实时消息推送（PRD 14.2）
from engine.rule_engine import RuleEngine  # 规则引擎 R01~R10（PRD 9.1，确定性）
from flow.approval_flow import ApprovalFlow  # 环节三 审批流转
from flow.attachment_flow import AttachmentFlow  # 环节二 附件管理
from flow.audit_log_flow import AuditLogFlow  # 环节七 操作审计
from flow.document_creation_flow import DocumentCreationFlow  # 环节一 单据创建
from flow.manual_review_flow import ManualReviewFlow  # 环节五 人工复核
from flow.report_export_flow import ReportExportFlow  # 环节六 报告导出
from flow.risk_analysis_flow import RiskAnalysisFlow  # 环节四 风险分析
from schema.enums import DocumentStatus  # 单据状态（resume 的重提前置状态判定）

__all__ = ["MainFlow"]

# 分析段的节点顺序：两张图共用（PRD 7.1 的下半段）
ANALYSIS_NODES = ("parse_attachments", "run_rules", "analyze", "compare_amounts", "report", "audit")
# 合同金额的抽取键名候选：PRD 未固定字段提取结果的键名，故按候选清单容错（与 engine 同口径）
CONTRACT_AMOUNT_KEYS = ("contract_amount", "contract_total_amount", "合同金额", "合同总额")


class MainFlow:
    """最外层主流程：装配七个环节与四个智能体，并用 LangGraph 驱动（PRD 2.7.1、7.1、8.1）。"""

    def __init__(self, llm: LLMClient, publisher: MessagePublisher) -> None:
        """装配七个环节与四个智能体；两张图各编译一次，可反复调用。"""
        # 步骤 1：创建四个智能体——与 PRD 20.2 的职责边界一一对应（本层只装配，不实现其职责）
        self.orchestrator = OrchestratorAgent(llm, publisher)  # A1 会话编排
        parser = DocumentParserAgent(llm, publisher)  # A2 凭证解析，供环节二、四使用
        analyst = RiskAnalystAgent(llm, publisher)    # A3 风险研判，供环节四使用
        reporter = ReporterAgent(llm, publisher)      # A4 报告留痕，供环节六使用
        # 步骤 2：先建操作审计（环节七），它是环节一、三、五共用的留痕出口（PRD 2.7.14）
        self.audit_log = AuditLogFlow()
        # 步骤 3：按 PRD 2.7.1 的顺序装配七个环节
        self.document_creation = DocumentCreationFlow(publisher, self.audit_log)  # 环节一
        self.attachment = AttachmentFlow(parser)                                  # 环节二
        self.approval = ApprovalFlow(publisher, self.audit_log)                   # 环节三
        self.risk_analysis = RiskAnalysisFlow(analyst)                            # 环节四
        self.manual_review = ManualReviewFlow(self.audit_log)                     # 环节五
        self.report_export = ReportExportFlow(reporter)                           # 环节六
        # 步骤 4：编译三张图（PRD 7.1 提交链路、PRD 8.1 多轮交互链路、PRD 13.6 单据分析）
        self.workflow_graph = self.build_graph().compile()
        self.intake_graph = self.build_intake_graph().compile()
        self.analysis_graph = self.build_analysis_graph().compile()

    # ---------- 节点：每个节点只做「调用对应环节 → 把产出回填状态」 ----------

    def _node_intake(self, state: dict) -> dict:
        """【A1 会话编排】识别意图、抽取并确认槽位、查单、派发与汇总（PRD 8.1、20.2）。"""
        # 步骤 1：交由 A1 处理多轮交互；单据与权限由服务层预取后传入（PRD 8.1 第 6 条）
        self.orchestrator.run(state["session"], state["user_message"], state.get("document"),
                              state.get("has_permission", False), state.get("task_id", 0),
                              state.get("report"))
        # 步骤 2：回填会话态，供后续节点与调用方使用
        state["slots"] = dict(self.orchestrator.slots)
        state["document"] = self.orchestrator.document
        state["summary"] = self.orchestrator.summary
        return state

    def _node_submit(self, state: dict) -> dict:
        """提交单据并生成快照、审批实例与首个审批任务（PRD 7.1-F/G、7.2）。"""
        state["snapshot"], state["instance"], state["approval_task"] = \
            self.document_creation.submit(state["document"], state["line_items"],
                                          state["first_node"], state["approver_id"])
        return state

    def _node_parse(self, state: dict) -> dict:
        """解析全部附件，产出结构化解析结果（PRD 7.1-H，交由 A2）。"""
        state["parse_results"] = [result for item in state["attachments"]
                                  if (result := self.attachment.parse(item)) is not None]
        return state

    def _node_rules(self, state: dict) -> dict:
        """执行规则引擎 R01~R10（PRD 9.1）——确定性计算，不调用大模型（PRD 20.1 P1）。"""
        # 步骤 1：规则配置由后端从 review_rules 读取后注入；未配置即无阈值，该规则不产出（PRD 20.7）
        # 步骤 2：直接把状态字典作为上下文——键名与规则引擎的约定一致，无需转换
        state["rule_results"] = RuleEngine(state.get("rules") or []).run(state)
        return state

    def _node_analyze(self, state: dict) -> dict:
        """创建分析任务并产出风险项与整体等级（PRD 7.1-I/J，交由 A3）。"""
        state["analysis_task"], state["findings"], state["overall_level"] = \
            self.risk_analysis.analyze(state["document"], state["line_items"],
                                       state["parse_results"], state["rule_results"])
        return state

    def _node_amounts(self, state: dict) -> dict:
        """金额核对：单据总金额、明细合计、发票合计、合同金额与付款金额对照（PRD 2.7.13）。"""
        # 步骤 1：合同金额优先取调用方传入值；未传入时从合同附件解析字段提取（PRD 12.1 表内无该列）
        contract_amount = state.get("contract_amount")
        if contract_amount is None:
            contract_amount = self.contract_amount_from(state.get("parse_results") or [])
        # 步骤 2：交环节四做确定性对照计算（差异与偏离比例均由此产出，PRD 9.3）
        state["amount_comparison"] = self.risk_analysis.compare_amounts(
            state["document"], state["line_items"], state["invoices"], contract_amount)
        return state

    @staticmethod
    def contract_amount_from(parse_results: list):
        """从合同类附件的解析字段中取合同金额，无法解析时返回 None（不臆造零值）。

        公开方法：供服务层在查询金额核对结果时复用，避免候选键名单出现第二份。
        """
        for result in parse_results:
            fields = result.fields_json or {}
            for key in CONTRACT_AMOUNT_KEYS:
                raw = fields.get(key)
                if raw in (None, ""):
                    continue
                text = str(raw)
                for symbol in ("¥", "￥", "$", ",", " ", "元"):
                    text = text.replace(symbol, "")
                try:
                    return Decimal(text)
                except Exception:
                    return None
        return None

    def _node_report(self, state: dict) -> dict:
        """生成风险审核报告与面板数据（PRD 7.1 末段，交由 A4）。

        单据实体与附件数量一并传入，使报告「单据摘要」章节引用的是真实字段而非模型臆测（PRD 15）。
        """
        state["report"] = self.report_export.generate(
            state["analysis_task"].id, state["document"], state["findings"],
            state["overall_level"], state["amount_comparison"], state.get("reviews") or [],
            len(state.get("attachments") or []))
        return state

    def _node_audit(self, state: dict) -> dict:
        """写入本次主流程的操作审计留痕（PRD 2.7.1 操作审计，只追加不改写）。"""
        state["audit_log"] = self.audit_log.record("analysis_task", "analysis_tasks",
                                                   state["analysis_task"].id)
        return state

    # ---------- 条件边 ----------

    def _after_intake(self, state: dict) -> str:
        """判定是否继续分析：单据已确认且通过权限校验才继续，否则结束等待用户补充（PRD 8.2）。"""
        return "analyze" if state.get("document") is not None else "wait_user"

    # ---------- 装配 ----------

    def _register_analysis_nodes(self, graph: StateGraph, start: str | None = None) -> None:
        """把分析段六个节点登记到图上；两张图共用，避免流程顺序出现两份事实。"""
        # 步骤 1：登记节点
        for name, handler in (("parse_attachments", self._node_parse),
                              ("run_rules", self._node_rules),
                              ("analyze", self._node_analyze),
                              ("compare_amounts", self._node_amounts),
                              ("report", self._node_report),
                              ("audit", self._node_audit)):
            graph.add_node(name, handler)
        # 步骤 2：按序连边；起始边按需登记（多轮交互图由条件边接入分析段）
        if start is not None:
            graph.add_edge(start, ANALYSIS_NODES[0])
        for previous, following in zip(ANALYSIS_NODES, ANALYSIS_NODES[1:] + (END,)):
            graph.add_edge(previous, following)

    def build_graph(self) -> StateGraph:
        """装配单据提交链路：提交 → 解析 → 规则 → 研判 → 核对 → 报告 → 留痕（PRD 7.1）。"""
        graph = StateGraph(dict)
        graph.add_node("submit", self._node_submit)
        graph.add_edge(START, "submit")
        self._register_analysis_nodes(graph, "submit")
        return graph

    def build_intake_graph(self) -> StateGraph:
        """装配多轮交互链路：A1 编排 → 分析段；槽位未齐则结束等待补充（PRD 8.1、8.2）。"""
        graph = StateGraph(dict)
        graph.add_node("intake", self._node_intake)
        # 步骤 1：起点为会话编排节点
        graph.add_edge(START, "intake")
        # 步骤 2：条件边——分析或等待用户补充；审批与复核由人工触发，不在自动段内
        graph.add_conditional_edges("intake", self._after_intake,
                                    {"analyze": ANALYSIS_NODES[0], "wait_user": END})
        # 步骤 3：登记分析段（起始边由上面的条件边承担）
        self._register_analysis_nodes(graph)
        return graph

    def build_analysis_graph(self) -> StateGraph:
        """装配单据风险分析链路：解析 → 规则 → 研判 → 核对 → 报告 → 留痕（PRD 13.6）。

        适用于已提交单据的分析请求，避免像提交链路那样重复生成快照与审批任务（PRD 7.2）。
        """
        graph = StateGraph(dict)
        # 步骤 1：起点直接接入分析段的解析节点
        graph.add_edge(START, ANALYSIS_NODES[0])
        # 步骤 2：登记分析段六个节点及其顺序
        self._register_analysis_nodes(graph)
        return graph

    # ---------- 驱动 ----------

    def run(self, state: dict) -> dict:
        """驱动单据提交链路执行一次完整主流程（PRD 7.1），返回执行后的状态。

        入参键：``document`` / ``line_items`` / ``attachments`` / ``rules``（审核规则配置，阈值来源）
        / ``invoices`` / ``contract_amount``（取自合同附件解析字段）/ ``first_node`` / ``approver_id``
        / ``reviews``（可选），以及规则引擎可选的 ``expense_standards`` / ``market_prices`` /
        ``supplier`` / ``invoice_history`` / ``expense_history`` 等参考数据。产出键：``snapshot`` /
        ``instance`` / ``approval_task`` / ``parse_results`` / ``rule_results`` /
        ``analysis_task`` /
        ``findings`` / ``overall_level`` / ``amount_comparison`` / ``report`` / ``audit_log``。
        权限校验与审批流程匹配属后端模块职责，须在调用前完成（PRD 20.1 P1）。"""
        # 步骤 1：交由装配好的图执行；图是流程顺序的唯一真源，本方法不重复编排
        return self.workflow_graph.invoke(state)

    def run_intake(self, state: dict) -> dict:
        """驱动多轮交互链路（PRD 8.1）。

        入参键：``session``（会话实体）/ ``user_message``（用户输入）/ ``document``（服务层按
        「单据类型 + 单据编号」预取的实体，未查到时为 None）/ ``has_permission``（数据权限判定结果）
        / ``task_id`` / ``report``，以及分析段所需的 ``line_items`` / ``attachments`` 等；
        产出键在提交链路基础上增加 ``slots`` 与 ``summary``（A1 的会话态与自然语言汇总）。"""
        # 步骤 1：交由多轮交互图执行；槽位未齐时图会在 A1 追问后直接结束
        return self.intake_graph.invoke(state)

    def run_analysis(self, state: dict) -> dict:
        """驱动单据风险分析链路（PRD 13.6 POST /documents/{document_id}/analysis）。

        入参键：``document`` / ``line_items`` / ``attachments`` / ``rules`` 及规则引擎可选的参考数据；
        产出键：``parse_results`` / ``rule_results`` / ``analysis_task`` / ``findings`` /
        ``overall_level`` / ``amount_comparison`` / ``report`` / ``audit_log``。
        与 ``run`` 的差别是不生成单据快照与审批实例——分析针对的已是提交后的单据（PRD 7.2）。"""
        # 步骤 1：交由分析段图执行
        return self.analysis_graph.invoke(state)

    def resume(self, state: dict) -> dict:
        """退回后重新提交：生成新版本与新的分析任务（PRD 7.2、7.3）。"""
        # 步骤 1：取单据并校验前置状态——仅 returned / withdrawn 可重新提交（PRD 7.3）
        document = state["document"]
        if document.document_status not in (DocumentStatus.RETURNED, DocumentStatus.WITHDRAWN):
            raise ValueError("仅已退回或已撤回的单据可重新提交（PRD 7.3）：%s" % document.document_status)
        # 步骤 2：复用主流程——提交会令版本号递增并重新生成实例、任务与分析（PRD 7.2）
        return self.run(state)
