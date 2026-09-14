"""规则引擎（PRD 2.7.9 规则引擎模块、9.1）。

职责：执行 PRD 9.1 的十条风险规则（R01~R10），产出 **A3 风险研判智能体直接消费的命中清单**。
A3 的 ``step3_run_rules`` 接收 ``rule_results: list[dict]``，``step4_build_findings`` 据此逐条构造
``RiskFinding``，读取的键为 ``risk_type`` / ``risk_level`` / ``risk_title`` 与四个 ``*_json``；
本引擎的输出即为该契约（见 ``rule_support.build_result``）。

边界（PRD 20.1 P1）：
* 本引擎负责**金额计算、阈值判定与规则命中**，全部为确定性实现，**不调用大模型**；
* 风险描述、业务归因与处理建议的措辞由 A3 的大模型环节撰写（PRD 20.4 L9、L10），本引擎不产出；
* 整体风险等级由 A3 按 PRD 9.2 判定表计算，本引擎只给**单项**等级；
* 本引擎**不修改规则与阈值**，只读取 ``review_rules`` / ``expense_standards`` /
  ``market_price_references`` / ``supplier_profiles``（PRD 20.2 A3 边界）。

规则分组（阈值一律取自规则配置；规则未配置或缺参考数据时该规则不产出，PRD 20.7）：
``amount_rules`` 实现 R01~R04；``expense_rules`` 实现 R05~R06；
``behavior_rules`` 实现 R07；``document_rules`` 实现 R08~R10。
"""

from engine.amount_rules import AmountRules  # R01~R04 金额与一致性
from engine.behavior_rules import BehaviorRules  # R07 消费行为异常
from engine.document_rules import DocumentRules  # R08~R10 供应商、附件、票据
from engine.expense_rules import ExpenseRules  # R05~R06 费用标准与市场价格
from schema.tables_rules import ReviewRule  # 审核规则配置：阈值的唯一来源（PRD 12.3 G07）

__all__ = ["RuleEngine"]


class RuleEngine:
    """规则引擎：执行 R01~R10 并汇总命中清单（PRD 2.7.9、9.1）。"""

    def __init__(self, rules: list[ReviewRule]) -> None:
        """装配四组规则；规则配置是阈值的唯一来源（PRD 12.3 G07）。"""
        # 步骤 1：持有规则表，供各规则组按编码取阈值
        self.rules = rules
        # 步骤 2：装配四组规则——分组只按主题拆分，执行顺序仍按 PRD 9.1 的 R01~R10
        self.amount = AmountRules(rules)
        self.expense = ExpenseRules(rules)
        self.behavior = BehaviorRules(rules)
        self.document = DocumentRules(rules)

    def run(self, context: dict) -> list[dict]:
        """执行全部规则，返回命中清单（无命中即为空列表）。

        ``context`` 需携带的数据（键名与 ``flow`` 层的状态字典保持一致，便于直接透传）：

        * ``document``：单据实体，**必填**（缺失即抛 ``KeyError``，不静默跳过）；
        * ``line_items``：单据明细；
        * ``parse_results``：附件解析结果（R03 取合同字段、R09 取分类与置信度）；
        * ``attachments``：附件实体（R09 判必需附件）；
        * ``invoices``：本单据的发票记录（R01、R10）；
        * ``invoice_history``：历史发票记录（R10 重复票据）；
        * ``expense_history``：历史明细（R07 历史金额突增）；
        * ``expense_standards``：费用标准（R05）；
        * ``market_prices``：市场价参考区间（R06）；
        * ``supplier``：供应商档案（R08）；
        * ``job_level``：申请人职级（R05；``users`` 与单据表均无该列，故由上下文传入）；
        * ``holidays``：节假日日历 ``set[date]``（R07）；
        * ``resident_region``：常驻地区（R07 异地异常消费）。

        除 ``document`` 外的键都按缺省处理：缺失即对应的规则不产出，不臆造数据（PRD 20.7）。
        """
        # 步骤 1：取上下文中的实体——除单据外一律按缺省处理，缺数据时由各规则自行跳过
        document = context["document"]           # 单据：必填，缺失即显式报错
        line_items = context.get("line_items") or []
        parse_results = context.get("parse_results") or []
        attachments = context.get("attachments") or []
        invoices = context.get("invoices") or []
        # 步骤 2：按 PRD 9.1 的编号顺序执行 R01~R04 并汇总
        results: list[dict] = []
        results += self.amount.check_invoice_consistency(document, invoices)          # R01
        results += self.amount.check_line_items_total(document, line_items)           # R02
        results += self.amount.check_contract_payment(document, parse_results)        # R03
        results += self.amount.check_batch_payment(document, line_items)              # R04
        # 步骤 3：执行 R05~R07——费用标准、市场价、消费行为
        results += self.expense.check_expense_standard(document, line_items,
                                                       context.get("expense_standards") or [],
                                                       context.get("job_level"))
        results += self.expense.check_market_price(document, line_items,
                                                   context.get("market_prices") or [])
        results += self.behavior.check_behavior_anomaly(document, line_items,
                                                         context.get("expense_history") or [],
                                                         context.get("holidays"),
                                                         context.get("resident_region"))
        # 步骤 4：执行 R08~R10——供应商、附件完整性、重复票据
        results += self.document.check_supplier_risk(document, line_items,
                                                     context.get("supplier"))
        results += self.document.check_attachment_completeness(document, attachments, parse_results)
        results += self.document.check_duplicate_invoice(document, invoices,
                                                          context.get("invoice_history") or [])
        # 步骤 5：返回命中清单——已按 R01~R10 排列，A3 可直接逐条构造风险项
        return results
