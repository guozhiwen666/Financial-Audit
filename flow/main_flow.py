"""最外层主流程（PRD 2.7.1 / 第 7 章 / 第 20 章）。

PRD 2.7.1 定义本系统覆盖七个环节：单据创建、附件管理、审批流转、风险分析、人工复核、报告导出、
操作审计。本模块只保留**装配与驱动**：把七个环节装配成 LangGraph 主流程并按序驱动，
各环节的职责分别落在同目录下的 ``*_flow.py``：

* 环节一 ``document_creation_flow.py``
* 环节二 ``attachment_flow.py``
* 环节三 ``approval_flow.py``
* 环节四 ``risk_analysis_flow.py``
* 环节五 ``manual_review_flow.py``
* 环节六 ``report_export_flow.py``
* 环节七 ``audit_log_flow.py``

本项目为多智能体协同：本层只做编排，**不承担任何业务规则**。金额合计与差异、规则命中、风险等级
取值、状态流转、权限校验一律由对应环节确定性实现，或由后端模块算出后传入（PRD 20.1 P1）；
大模型只在 A2 / A3 / A4 内部使用，智能体只产出结论（PRD 20.1 P4）。审批与复核由人工触发，
不在自动段内（PRD 2.7.14 要求最终审批结果由有权限的人员人工确认）。
"""

from langgraph.graph import END, START, StateGraph  # 主流程装配（PRD 7.1）

from agent.document_parser_agent.main_flow import DocumentParserAgent  # A2 凭证解析
from agent.reporter_agent.main_flow import ReporterAgent  # A4 报告留痕
from agent.risk_analyst_agent.main_flow import RiskAnalystAgent  # A3 风险研判
from agent.utils.llm import LLMClient  # 大模型调用：由本层创建后注入各智能体（PRD 20.4）
from agent.utils.message import MessagePublisher  # 实时消息推送（PRD 14.2）
from flow.approval_flow import ApprovalFlow  # 环节三 审批流转
from flow.attachment_flow import AttachmentFlow  # 环节二 附件管理
from flow.audit_log_flow import AuditLogFlow  # 环节七 操作审计
from flow.document_creation_flow import DocumentCreationFlow  # 环节一 单据创建
from flow.manual_review_flow import ManualReviewFlow  # 环节五 人工复核
from flow.report_export_flow import ReportExportFlow  # 环节六 报告导出
from flow.risk_analysis_flow import RiskAnalysisFlow  # 环节四 风险分析
from schema.enums import DocumentStatus  # 单据状态（resume 的重提前置状态判定）

__all__ = ["MainFlow"]


class MainFlow:
    """最外层主流程：装配七个环节并驱动其状态流转（PRD 2.7.1、7.1、7.3）。"""

    def __init__(self, llm: LLMClient, publisher: MessagePublisher) -> None:
        """装配七个环节；A2 / A3 / A4 三个下游智能体由本层创建并注入需要它们的环节。"""
        # 步骤 1：创建下游智能体——与 PRD 20.2 的职责边界一一对应（本层只装配，不实现其职责）
        parser = DocumentParserAgent(llm, publisher)  # 供环节二、环节四使用
        analyst = RiskAnalystAgent(llm, publisher)    # 供环节四使用
        reporter = ReporterAgent(llm, publisher)      # 供环节六使用
        # 步骤 2：先建操作审计（环节七），它是环节一、三、五共用的留痕出口（PRD 2.7.14）
        self.audit_log = AuditLogFlow()
        # 步骤 3：按 PRD 2.7.1 的顺序装配七个环节
        self.document_creation = DocumentCreationFlow(publisher, self.audit_log)  # 环节一
        self.attachment = AttachmentFlow(parser)                                  # 环节二
        self.approval = ApprovalFlow(publisher, self.audit_log)                   # 环节三
        self.risk_analysis = RiskAnalysisFlow(analyst)                            # 环节四
        self.manual_review = ManualReviewFlow(self.audit_log)                     # 环节五
        self.report_export = ReportExportFlow(reporter)                           # 环节六
        # 步骤 4：装配并编译主流程图，装配一次即可复用（PRD 7.1）
        self.graph = self.build_graph().compile()

    def build_graph(self) -> StateGraph:
        """装配主流程：提交 → 附件解析 → 风险分析 → 报告生成 → 操作审计（PRD 7.1）。"""
        def submit(state: dict) -> dict:
            """提交单据并生成快照、审批实例与首个审批任务（PRD 7.1-F / G）。"""
            state["snapshot"], state["instance"], state["approval_task"] = \
                self.document_creation.submit(state["document"], state["line_items"],
                                             state["first_node"], state["approver_id"])
            return state
        def parse(state: dict) -> dict:
            """解析全部附件，产出结构化解析结果（PRD 7.1-H，交由 A2）。"""
            state["parse_results"] = [result for item in state["attachments"]
                                      if (result := self.attachment.parse(item)) is not None]
            return state
        def analyze(state: dict) -> dict:
            """创建分析任务并产出风险项与整体等级（PRD 7.1-I / J，交由 A3）。"""
            state["analysis_task"], state["findings"], state["overall_level"] = \
                self.risk_analysis.analyze(state["document"], state["line_items"],
                                           state["parse_results"], state["rule_results"])
            return state
        def report(state: dict) -> dict:
            """金额核对并生成风险审核报告（PRD 7.1 末段，交由 A3 的金额核对与 A4）。"""
            state["amount_comparison"] = self.risk_analysis.compare_amounts(
                state["document"], state["line_items"], state["invoices"], state["contract_amount"])
            state["report"] = self.report_export.generate(
                state["analysis_task"].id, state["document"].id, state["findings"],
                state["overall_level"], state["amount_comparison"], state.get("reviews") or [])
            return state
        def audit(state: dict) -> dict:
            """写入本次主流程的操作审计留痕（PRD 2.7.1 操作审计）。"""
            state["audit_log"] = self.audit_log.record("analysis_task", "analysis_tasks",
                                                       state["analysis_task"].id)
            return state
        # 步骤 1：状态用 dict 承载环节间传递，不新增数据结构
        # 步骤 2：逐节点登记——每个节点只做「调用对应环节 → 把产出回填状态」
        graph = StateGraph(dict)
        for name, handler in (("submit", submit), ("parse_attachments", parse),
                              ("analyze", analyze), ("report", report), ("audit", audit)):
            graph.add_node(name, handler)
        # 步骤 3：按 PRD 7.1 的顺序连边；审批与复核由人工触发，故不在自动段内
        graph.add_edge(START, "submit")
        order = ("submit", "parse_attachments", "analyze", "report", "audit")
        for previous, following in zip(order, order[1:] + (END,)):
            graph.add_edge(previous, following)
        # 步骤 4：返回装配好的图，由调用方编译或直接编译（PRD 7.1）
        return graph

    def run(self, state: dict) -> dict:
        """从单据提交开始执行一次完整主流程（PRD 7.1），返回执行后的状态。

        入参键：``document`` / ``line_items`` / ``attachments`` / ``rule_results``（规则引擎执行结果，
        市场价与供应商比对已含其中）/ ``invoices`` / ``contract_amount``（取自合同附件解析字段）/
        ``first_node`` / ``approver_id`` / ``reviews``（可选）；产出键：``snapshot`` / ``instance``
        / ``approval_task`` / ``parse_results`` / ``analysis_task`` / ``findings`` / ``overall_level``
        / ``amount_comparison`` / ``report`` / ``audit_log``。权限校验与审批流程匹配属后端模块职责，
        须在调用前完成（PRD 20.1 P1）。"""
        # 步骤 1：交由装配好的图执行；图是流程顺序的唯一真源，本方法不重复编排
        return self.graph.invoke(state)

    def resume(self, state: dict) -> dict:
        """退回后重新提交：生成新版本与新的分析任务（PRD 7.2、7.3）。"""
        # 步骤 1：取单据并校验前置状态——仅 returned / withdrawn 可重新提交（PRD 7.3）
        document = state["document"]
        if document.document_status not in (DocumentStatus.RETURNED, DocumentStatus.WITHDRAWN):
            raise ValueError("仅已退回或已撤回的单据可重新提交（PRD 7.3）：%s" % document.document_status)
        # 步骤 2：复用主流程——提交会令版本号递增并重新生成实例、任务与分析（PRD 7.2）
        return self.run(state)
