"""R07 消费行为异常规则（PRD 9.1）。

PRD 9.1 R07 列举了六种异常行为：短期高频消费、同日重复报销、节假日异常消费、异地异常消费、
拆单报销、历史金额突增；输出为「异常类型、触发条件」。本模块逐项识别，命中即记入异常清单。

**取值来源约定（PRD 未列举，属本引擎与规则配置之间的接口约定，需与用户确认）**：
* PRD 只列举了行为名、未给任何阈值，故阈值一律取自 ``params_json``；
* 缺阈值、或缺该子模式所依赖的参考数据时，**该子模式不产出**，不臆造阈值（PRD 20.7）；
* 三项数据在既有表中无字段，由调用方随上下文传入：节假日日历、常驻地区、历史明细。
"""

from datetime import date  # date：节假日判定与消费日期跨度计算
from decimal import Decimal  # Decimal：金额与比例，禁止 float

from engine.rule_support import (  # 规则引擎公共件
    as_decimal, build_result, find_rule, params_of, to_ratio_text, to_text,
)
from schema.tables_document import DocumentLineItem, FinancialDocument  # 单据与明细
from schema.tables_rules import ReviewRule  # 规则配置（阈值的唯一来源）

__all__ = ["BehaviorRules", "R07_BEHAVIOR"]

# 本模块实现的规则编码（PRD 9.1）
R07_BEHAVIOR = "R07"  # 消费行为异常

# 六种异常行为的阈值键名（PRD 未给阈值，故全部由规则配置给出）
KEY_WINDOW_DAYS = "window_days"            # 短期高频 / 拆单：观察窗口天数
KEY_MIN_COUNT = "min_count"                # 短期高频 / 拆单：窗口内最小笔数
KEY_SPLIT_MAX_AMOUNT = "split_max_amount"  # 拆单：单笔金额上限
KEY_SURGE_RATIO = "surge_ratio"            # 历史金额突增：超出历史均值的比例上限


class BehaviorRules:
    """R07：消费行为异常（PRD 9.1 R07）。"""

    def __init__(self, rules: list[ReviewRule]) -> None:
        """保存规则配置表；阈值按规则编码取（PRD 12.3 G07）。"""
        # 步骤 1：持有规则表，本规则据此取阈值与等级档位
        self.rules = rules

    def check_behavior_anomaly(self, document: FinancialDocument,
                               line_items: list[DocumentLineItem],
                               expense_history: list[DocumentLineItem],
                               holidays: set[date] | None = None,
                               resident_region: str | None = None) -> list[dict]:
        """识别六种消费行为异常，命中即产出风险项（PRD 9.1 R07）。

        ``holidays`` 与 ``resident_region`` 缺失时，对应的两种子模式不产出；
        ``expense_history`` 为空时「历史金额突增」不产出（PRD 20.7）。
        """
        # 步骤 1：取规则配置；未配置则规则整体跳过（PRD 20.7）
        rule = find_rule(self.rules, R07_BEHAVIOR)
        if rule is None:
            return []
        # 步骤 2：取出阈值参数，供各子模式使用
        params = params_of(rule)
        # 步骤 3：逐项识别，命中即追加到异常清单（PRD 9.1 R07 的输出为异常类型与触发条件）
        anomalies: list[dict] = []
        anomalies += self._high_frequency(line_items, params)
        anomalies += self._same_day_duplicate(line_items)
        anomalies += self._holiday_expense(line_items, holidays)
        anomalies += self._remote_location(document, line_items, resident_region)
        anomalies += self._split_reimbursement(line_items, params)
        anomalies += self._amount_surge(document, expense_history, params)
        # 步骤 4：无异常则未命中
        if not anomalies:
            return []
        # 步骤 5：组装结果——异常清单作为计算值，所用阈值作为对比值（PRD 9.3）
        return [build_result(rule, "存在 %d 项消费行为异常" % len(anomalies),
                             actual={"anomalies": anomalies},
                             reference={"window_days": params.get(KEY_WINDOW_DAYS),
                                        "min_count": params.get(KEY_MIN_COUNT),
                                        "surge_ratio": params.get(KEY_SURGE_RATIO)},
                             evidence={"document_id": document.id,
                                       "line_item_ids": [i.id for i in line_items]})]

    @staticmethod
    def _window_groups(line_items: list[DocumentLineItem], params: dict, cap: Decimal | None
                       ) -> dict[str, list[DocumentLineItem]]:
        """按名称分组，只保留「有消费日期、有金额、（可选）金额不超单笔上限」的行。

        用于「短期高频消费」与「拆单报销」两个子模式：前者不限单笔金额，后者限单笔上限。
        """
        # 步骤 1：取窗口与笔数阈值；缺任一即返回空，由调用方视为不产出（PRD 20.7）
        if (as_decimal(params.get(KEY_WINDOW_DAYS)) is None
                or as_decimal(params.get(KEY_MIN_COUNT)) is None):
            return {}
        # 步骤 2：逐行归组——名称、消费日期与金额缺一不可；给了单笔上限时还要满足不超上限
        groups: dict[str, list[DocumentLineItem]] = {}
        for item in line_items:
            if not item.item_name or item.expense_date is None or item.amount is None:
                continue
            if cap is not None and item.amount > cap:
                continue
            groups.setdefault(to_text(item.item_name), []).append(item)
        # 步骤 3：返回分组结果，供各子模式按窗口与笔数判定
        return groups

    @classmethod
    def _high_frequency(cls, line_items: list[DocumentLineItem], params: dict) -> list[dict]:
        """短期高频消费：同名明细在窗口天数内出现次数达到下限（PRD 9.1 R07）。"""
        # 步骤 1：分组——本子模式不限单笔金额，故 cap 传 None
        groups = cls._window_groups(line_items, params, None)
        window = int(as_decimal(params[KEY_WINDOW_DAYS]))
        minimum = int(as_decimal(params[KEY_MIN_COUNT]))
        # 步骤 2：跨度不超过窗口且笔数达到下限即命中
        hits = []
        for name, items in groups.items():
            days = [i.expense_date for i in items]
            span = (max(days) - min(days)).days
            if span <= window and len(items) >= minimum:
                hits.append({"type": "短期高频消费",
                             "trigger": "「%s」在 %d 天内出现 %d 次" % (name, span, len(items))})
        return hits

    @staticmethod
    def _same_day_duplicate(line_items: list[DocumentLineItem]) -> list[dict]:
        """同日重复报销：同一消费日期与同一金额出现多次（PRD 9.1 R07）。"""
        # 步骤 1：按「消费日期 + 金额」统计出现次数——该子模式无需阈值即可判定
        counted: dict[tuple, int] = {}
        for item in line_items:
            if item.expense_date is not None and item.amount is not None:
                key = (item.expense_date, item.amount)
                counted[key] = counted.get(key, 0) + 1
        # 步骤 2：出现次数大于 1 即命中
        return [{"type": "同日重复报销",
                 "trigger": "%s 出现 %d 笔金额 %s 的消费" % (key[0].isoformat(), count, key[1])}
                for key, count in counted.items() if count > 1]

    @staticmethod
    def _holiday_expense(line_items: list[DocumentLineItem],
                         holidays: set[date] | None) -> list[dict]:
        """节假日异常消费：消费日期落在节假日日历内（PRD 9.1 R07）。"""
        # 步骤 1：未提供节假日日历则不产出该子模式（PRD 20.7 数据不足）
        if not holidays:
            return []
        # 步骤 2：逐行判断消费日期是否命中节假日
        return [{"type": "节假日异常消费", "trigger": "%s 为节假日" % item.expense_date.isoformat()}
                for item in line_items if item.expense_date in holidays]

    @staticmethod
    def _remote_location(document: FinancialDocument, line_items: list[DocumentLineItem],
                         resident_region: str | None) -> list[dict]:
        """异地异常消费：消费地点既非常驻地区，也非本单出差地点（PRD 9.1 R07）。"""
        # 步骤 1：常驻地区未提供则不产出该子模式（PRD 20.7 数据不足）
        if not resident_region:
            return []
        # 步骤 2：合法范围＝常驻地区；差旅报销单另并入出差地点（多地点以「、」分隔）
        allowed = {to_text(resident_region)}
        if document.travel_destination:
            allowed.update(part.strip() for part in document.travel_destination.split("、") if part)
        # 步骤 3：消费地点不在合法范围内即命中
        return [{"type": "异地异常消费",
                 "trigger": "消费地点「%s」不在常驻地或出差地「%s」范围内"
                            % (item.expense_location, "、".join(sorted(allowed)))}
                for item in line_items
                if item.expense_location and to_text(item.expense_location) not in allowed]

    @classmethod
    def _split_reimbursement(cls, line_items: list[DocumentLineItem], params: dict) -> list[dict]:
        """拆单报销：同名明细在窗口内多次出现，且每笔均不超单笔上限（PRD 9.1 R07）。"""
        # 步骤 1：取单笔上限；未配置则不产出该子模式（PRD 20.7）
        cap = as_decimal(params.get(KEY_SPLIT_MAX_AMOUNT))
        if cap is None:
            return []
        # 步骤 2：分组——只保留金额不超单笔上限的行
        groups = cls._window_groups(line_items, params, cap)
        window = int(as_decimal(params[KEY_WINDOW_DAYS]))
        minimum = int(as_decimal(params[KEY_MIN_COUNT]))
        # 步骤 3：窗口内笔数达到下限即命中拆单特征
        hits = []
        for name, items in groups.items():
            days = [i.expense_date for i in items]
            span = (max(days) - min(days)).days
            if span <= window and len(items) >= minimum:
                hits.append({"type": "拆单报销",
                             "trigger": "「%s」在 %d 天内拆为 %d 笔，单笔均不超过 %s"
                                        % (name, span, len(items), cap)})
        return hits

    @staticmethod
    def _amount_surge(document: FinancialDocument, expense_history: list[DocumentLineItem],
                      params: dict) -> list[dict]:
        """历史金额突增：本次单据金额超出历史明细均值的比例上限（PRD 9.1 R07）。"""
        # 步骤 1：取比例上限与本次金额；缺阈值、历史为空或本次金额缺失则不产出（PRD 20.7）
        limit = as_decimal(params.get(KEY_SURGE_RATIO))
        current = document.total_amount
        if limit is None or current is None or not expense_history:
            return []
        # 步骤 2：算历史明细金额均值（确定性求和 + 均值；跳过金额缺失的行）
        amounts = [item.amount for item in expense_history if item.amount is not None]
        if not amounts:
            return []
        average = sum(amounts, Decimal(0)) / Decimal(len(amounts))
        # 步骤 3：均值为 0 时比例无意义，不产出
        if not average:
            return []
        # 步骤 4：超出比例上限即命中
        ratio = (current - average) / average
        if ratio <= limit:
            return []
        return [{"type": "历史金额突增",
                 "trigger": "本次金额 %s 超历史均值 %s 的 %s 倍"
                            % (current, average, to_ratio_text(ratio))}]
