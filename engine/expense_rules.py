"""R05~R06 费用与价格类规则（PRD 9.1）。

| 编码 | 规则 | 输出（PRD 9.1） |
|---|---|---|
| R05 | 费用标准合规性 | 超出金额、适用标准值 |
| R06 | 市场价格合理性 | 价格偏离比例、参考区间 |

边界（PRD 20.1 P1）：本模块全部为确定性比对，不调用大模型。
参考数据缺失时**不产出该风险项**（PRD 20.7），不臆造标准值或参考区间。

**取值来源约定（PRD 未列举，属本引擎与规则配置之间的接口约定，需与用户确认）**：
* 费用标准的「职级」维度在 ``users`` 与单据表中均无对应列，故由调用方随上下文传入，缺失即跳过该维度；
* 费用标准的「地区」维度取自明细行的消费地点（单据无地区字段）；
* 费用类别取自单据（明细行无该字段，只有费用科目）。
"""

from datetime import date  # date：生效日期与消费日期的比较
from decimal import Decimal  # Decimal：金额与比例，禁止 float

from engine.rule_support import (  # 规则引擎公共件
    build_result, find_rule, to_ratio_text, to_text,
)
from schema.tables_document import DocumentLineItem, FinancialDocument  # 单据与明细
from schema.tables_reference import MarketPriceReference  # 市场价参考区间（R06 数据来源）
from schema.tables_rules import ExpenseStandard, ReviewRule  # 费用标准与规则配置

__all__ = ["ExpenseRules", "R05_STANDARD", "R06_MARKET_PRICE"]

# 本模块实现的规则编码（PRD 9.1）
R05_STANDARD = "R05"      # 费用标准合规性
R06_MARKET_PRICE = "R06"  # 市场价格合理性


class ExpenseRules:
    """R05~R06：费用与价格类规则（PRD 9.1）。"""

    def __init__(self, rules: list[ReviewRule]) -> None:
        """保存规则配置表；每条规则按编码取自己的阈值（PRD 12.3 G07）。"""
        # 步骤 1：持有规则表，各规则据此取阈值与等级档位
        self.rules = rules

    def check_expense_standard(self, document: FinancialDocument,
                               line_items: list[DocumentLineItem],
                               standards: list[ExpenseStandard],
                               job_level: str | None = None) -> list[dict]:
        """R05：按费用类别、预算部门、职级、地区与日期匹配费用标准，超出上限即命中（PRD 9.1 R05）。"""
        # 步骤 1：取规则配置；未配置或无标准数据则规则整体跳过（PRD 20.7）
        rule = find_rule(self.rules, R05_STANDARD)
        if rule is None or not standards:
            return []
        # 步骤 2：逐条明细匹配适用标准并比对
        overages: list[dict] = []
        for item in line_items:
            # 步骤 2.1：筛出适用标准并取生效最新的一条；无适用标准则该行不做判定
            applicable = [s for s in standards
                          if self._standard_applies(document, item, s, job_level)]
            if not applicable or item.amount is None:
                continue
            standard = max(applicable, key=lambda s: (s.effective_date or date.min, s.id))
            if standard.standard_amount is None:
                continue
            # 步骤 2.2：仅在同币种下比对金额，避免跨币种直接比大小（币种缺失视为同币种）
            standard_currency = to_text(standard.currency)
            if standard_currency and standard_currency != to_text(document.currency):
                continue
            # 步骤 2.3：超出标准上限即命中，记录超出金额与适用标准值（PRD 9.1 R05 的输出）
            if item.amount > standard.standard_amount:
                overages.append({"line_item_id": item.id, "item_name": item.item_name,
                                 "amount": str(item.amount),
                                 "standard_amount": str(standard.standard_amount),
                                 "overage": str(item.amount - standard.standard_amount),
                                 "standard_id": standard.id})
        # 步骤 3：无超标行则未命中
        if not overages:
            return []
        # 步骤 4：组装结果——超出金额明细作为计算值，匹配维度作为对比值（PRD 9.3）
        return [build_result(rule, "存在 %d 项费用超出标准" % len(overages),
                             actual={"overages": overages},
                             reference={"expense_category": document.expense_category,
                                        "budget_department": document.budget_department,
                                        "job_level": job_level},
                             evidence={"document_id": document.id,
                                       "line_item_ids": [o["line_item_id"] for o in overages]})]

    def check_market_price(self, document: FinancialDocument, line_items: list[DocumentLineItem],
                           market_prices: list[MarketPriceReference]) -> list[dict]:
        """R06：按名称、地区与时间匹配市场价参考区间，计算偏离比例（PRD 9.1 R06）。"""
        # 步骤 1：取规则配置；未配置或无参考数据则规则整体跳过（PRD 20.7）
        rule = find_rule(self.rules, R06_MARKET_PRICE)
        if rule is None or not market_prices:
            return []
        # 步骤 2：逐条明细比对单价——单价缺失或参考价缺失的行不判定
        deviations: list[dict] = []
        for item in line_items:
            reference = self._match_price(item, market_prices)
            if reference is None or item.unit_price is None:
                continue
            # 步骤 2.1：算偏离比例——高于上限按上限算，低于下限按下限算（PRD 9.1 R06）
            deviation = self._price_deviation(item.unit_price, reference)
            if deviation is None:
                continue  # 落在参考区间内
            deviations.append({"line_item_id": item.id, "item_name": item.item_name,
                               "unit_price": str(item.unit_price),
                               "price_min": None if reference.price_min is None
                               else str(reference.price_min),
                               "price_max": None if reference.price_max is None
                               else str(reference.price_max),
                               "ratio": to_ratio_text(deviation), "reference_id": reference.id,
                               "source_name": reference.source_name})
        # 步骤 3：无偏离行则未命中
        if not deviations:
            return []
        # 步骤 4：整体偏离比例取最大者，供按档位判定单项等级（PRD 9.2）
        worst = max(Decimal(d["ratio"]) for d in deviations)
        # 步骤 5：组装结果——偏离比例与参考区间（PRD 9.1 R06 的输出）
        return [build_result(rule, "存在 %d 项单价偏离市场价区间" % len(deviations), ratio=worst,
                             actual={"deviations": deviations},
                             reference={"market_price_source": "market_price_references"},
                             evidence={"document_id": document.id,
                                       "line_item_ids": [d["line_item_id"] for d in deviations]})]

    @staticmethod
    def _standard_applies(document: FinancialDocument, item: DocumentLineItem,
                          standard: ExpenseStandard, job_level: str | None) -> bool:
        """判断某条费用标准是否适用于该明细行：逐维度比对，标准侧未填写的维度不参与判定。"""
        # 步骤 1：费用类别——标准侧填写时须与单据费用类别一致
        if standard.expense_category and to_text(standard.expense_category) != to_text(
                document.expense_category):
            return False
        # 步骤 2：部门——标准侧填写时须与预算部门一致
        if standard.department and to_text(standard.department) != to_text(
                document.budget_department):
            return False
        # 步骤 3：职级——标准侧填写时须与传入职级一致（职级无表字段，由上下文传入）
        if standard.job_level and to_text(standard.job_level) != to_text(job_level):
            return False
        # 步骤 4：地区——标准侧填写时须与明细消费地点一致
        if standard.region and to_text(standard.region) != to_text(item.expense_location):
            return False
        # 步骤 5：生效日期——须不晚于消费日期（消费日期缺失时退回单据申请日期）
        consumed = item.expense_date or document.apply_date
        if standard.effective_date and consumed and standard.effective_date > consumed:
            return False
        # 步骤 6：五个维度均通过即适用
        return True

    @staticmethod
    def _match_price(item: DocumentLineItem,
                     market_prices: list[MarketPriceReference]) -> MarketPriceReference | None:
        """按名称、地区与生效日期筛出参考价，取生效最新的一条；无匹配返回 None。"""
        # 步骤 1：筛选——名称须一致；参考数据填写了地区时才要求地区一致；生效日期须不晚于消费日期
        applicable = []
        for reference in market_prices:
            if to_text(reference.item_name) != to_text(item.item_name):
                continue
            if reference.region and to_text(reference.region) != to_text(item.expense_location):
                continue
            if (reference.effective_date and item.expense_date
                    and reference.effective_date > item.expense_date):
                continue
            applicable.append(reference)
        if not applicable:
            return None
        # 步骤 2：取生效日期最新者；同日期取主键较大者，保证结果与集合顺序无关
        return max(applicable, key=lambda r: (r.effective_date or date.min, r.id))

    @staticmethod
    def _price_deviation(unit_price: Decimal, reference: MarketPriceReference) -> Decimal | None:
        """算单价相对参考区间的偏离比例；落在区间内返回 None。"""
        # 步骤 1：高于上限——偏离比例＝（单价 − 上限）/ 上限
        if reference.price_max is not None and unit_price > reference.price_max:
            return ((unit_price - reference.price_max) / reference.price_max
                    if reference.price_max else None)
        # 步骤 2：低于下限——偏离比例＝（下限 − 单价）/ 下限
        if reference.price_min is not None and unit_price < reference.price_min:
            return ((reference.price_min - unit_price) / reference.price_min
                    if reference.price_min else None)
        # 步骤 3：落在区间内即无偏离
        return None
