"""环节四 风险分析（PRD 2.7.1 分析能力、9.1、2.7.13）。

职责：创建风险分析任务、聚合单据与明细与附件解析结果与规则结果，交由 **A3 风险研判智能体** 产出
风险项与整体等级；并提供金额核对（单据总金额 / 明细合计 / 发票合计 / 合同金额 / 付款金额）。

边界（PRD 20.1 P1、20.2 A3）：
* 市场价参考数据与供应商资料经规则引擎（R06 / R08）比对后体现在 ``rule_results`` 中，本环节不自行比对；
* 金额与差异一律取自规则结果或做纯确定性合计，本环节不调用大模型；
* 整体风险等级由 A3 按 PRD 9.2 判定表计算，本环节不重新判定。
"""

from datetime import datetime, timezone  # 分析任务起止时间（PRD 12.2：时间戳统一 UTC）
from decimal import Decimal  # 金额，禁止 float 以免精度丢失

from agent.risk_analyst_agent.main_flow import RiskAnalystAgent  # A3 风险研判智能体
from schema.enums import AnalysisTaskStatus, RiskLevel  # 分析任务状态、风险等级
from schema.tables_analysis import AnalysisTask, RiskFinding  # 分析任务、风险项
from schema.tables_document import (  # 单据、明细、解析结果、发票记录
    AttachmentParseResult, DocumentLineItem, FinancialDocument, InvoiceRecord,
)

__all__ = ["RiskAnalysisFlow"]


class RiskAnalysisFlow:
    """环节四 风险分析（PRD 2.7.1 分析能力、9.1）。"""

    def __init__(self, analyst: RiskAnalystAgent) -> None:
        """注入下游研判智能体。"""
        self.analyst = analyst  # 研判交由 A3 风险研判智能体（PRD 20.2）

    def analyze(self, document: FinancialDocument, line_items: list[DocumentLineItem],
                parse_results: list[AttachmentParseResult],
                rule_results: list[dict]) -> tuple[AnalysisTask, list[RiskFinding], RiskLevel]:
        """创建风险分析任务：聚合单据、明细、附件解析结果与规则结果，产出风险项与整体等级。

        附件加载与解析阶段的进度由环节二以 attachment_status 消息体现，本任务只记录 A3 自身的阶段。
        """
        # 步骤 1：创建分析任务——主键待落库后回填故以 0 占位；初始状态排队中（PRD 2.7.12 任务状态）
        task = AnalysisTask(id=0,
                            document_id=document.id,        # 被分析的单据
                            task_status=AnalysisTaskStatus.QUEUED,
                            current_step="排队中",           # 当前步骤，供前端展示进度说明
                            started_at=datetime.now(timezone.utc))
        # 步骤 2：推进到「分析中」——聚合已完成，本步开始执行规则校验与风险判定（PRD 7.1-J）
        task.task_status, task.current_step = AnalysisTaskStatus.ANALYZING, "分析中"
        # 步骤 3：交 A3 研判——输入单据、明细、附件解析结果与规则结果，输出风险项与整体等级
        findings, overall_level = self.analyst.run(task.id, document, line_items,
                                                   parse_results, rule_results)
        # 步骤 4：任务收尾——置成功、记录完成步骤与结束时间（PRD 2.7.12 分析任务状态）
        task.task_status, task.current_step = AnalysisTaskStatus.SUCCEEDED, "已完成"
        task.finished_at = datetime.now(timezone.utc)
        # 步骤 5：返回任务与结论，供调用方落库并触发报告生成
        return task, findings, overall_level

    def compare_amounts(self, document: FinancialDocument, line_items: list[DocumentLineItem],
                        invoices: list[InvoiceRecord], contract_amount: Decimal | None) -> dict:
        """金额核对：单据总金额、明细合计、发票合计、合同金额与付款金额对照（PRD 2.7.13）。

        全部为确定性计算并输出各项差异与偏离比例（PRD 9.3 要求展示计算值与对比值）；
        合同金额取自合同附件的解析字段（本表无该列，故由调用方传入），
        付款金额取单据支出金额（PRD 5.2 ``amount``）。
        """
        # 步骤 1：汇总五个口径——单据总金额作为差异比对基准
        amounts = {
            "document_amount": document.total_amount,   # 单据总金额（基准）
            "line_item_total": sum((i.amount or Decimal(0) for i in line_items), Decimal(0)),
            "invoice_total": sum((i.amount_including_tax or Decimal(0) for i in invoices),
                                 Decimal(0)),
            "contract_amount": contract_amount,         # 合同金额：来自合同附件解析字段
            "payment_amount": document.amount,          # 付款金额：单据支出金额（PRD 5.2）
        }
        # 步骤 2：计算各项与基准的差异金额（缺失口径保持 None，不做零值臆测）
        base = document.total_amount or Decimal(0)
        differences = {n: (v - base) if v is not None else None for n, v in amounts.items()}
        # 步骤 3：计算偏离比例——基准为 0 时无法计算，置 None（PRD 9.1 R01 要求输出差异比例）
        ratios = {n: ((v / base) if base else None) if v is not None else None
                  for n, v in differences.items()}
        # 步骤 4：Decimal 与 None 均不能直接进 JSON 列，统一转字符串（与 PRD 9.3 取值示例一致）
        return {"amounts": {k: (None if v is None else str(v)) for k, v in amounts.items()},
                "differences": {k: (None if v is None else str(v)) for k, v in differences.items()},
                "deviation_ratios": {k: (None if v is None else str(v)) for k, v in ratios.items()}}
