"""规则引擎的公共辅助（PRD 9.1、9.2、9.3）。

PRD 9.1 的 R01~R10 分三组实现，但四件事是共用的：按编码取规则配置、把 JSON 列里的取值转成
``Decimal`` / ``date``、按 PRD 9.3 组装命中结果、按偏离比例判定单项风险等级。
本模块只放这些公共件，不含任何规则逻辑。

**关于取值来源的约定（PRD 未列举，属本引擎与规则配置之间的接口约定，需与用户确认后方可视为定稿）**：

* 阈值一律取自 ``ReviewRule.params_json``——PRD 9.3 的示例即 ``{"tolerance": "100.00", "rule_id": "R01"}`；
* 金额容差键 ``tolerance``；等级分档键 ``medium_ratio`` / ``high_ratio``；二元命中的固定等级键 ``level``；
* 三项都缺时按 PRD 9.2 的最低档 ``low`` 处理（9.2 枚举注释：低风险＝存在轻微差异，通常不影响审批）；
* **规则未配置（``rule_code`` 不在规则表中）时该规则整体跳过**，不臆造阈值
  （PRD 20.7：参考数据缺失时不产出该风险项）。
"""

from datetime import date  # date：参考数据生效日期
from decimal import Decimal, InvalidOperation  # Decimal：金额与比例，禁止 float
from typing import Any  # Any：params_json 与 *_json 列的取值类型不固定

from schema.enums import RiskLevel  # 单项风险等级（PRD 9.2）
from schema.tables_rules import ReviewRule  # 审核规则配置（PRD 12.3 G07）

__all__ = ["find_rule", "params_of", "as_decimal", "as_date", "to_text", "decide_level",
           "build_result", "to_ratio_text", "KEY_TOLERANCE", "KEY_MEDIUM_RATIO",
           "KEY_HIGH_RATIO", "KEY_LEVEL"]

# params_json 的约定键名（PRD 未列举；tolerance 取自 PRD 9.3 的示例）
KEY_TOLERANCE = "tolerance"        # 金额容差：差异绝对值超过它即命中
KEY_MEDIUM_RATIO = "medium_ratio"  # 中风险档：偏离比例达到该值即判 medium
KEY_HIGH_RATIO = "high_ratio"      # 高风险档：偏离比例达到该值即判 high
KEY_LEVEL = "level"                # 固定等级：二元命中型规则（黑名单、重复票据等）使用

# 偏离比例的展示小数位（PRD 未规定精度；不设上限时除法的原始结果可达 29 位，不宜直接展示）
RATIO_DIGITS = 6


def find_rule(rules: list[ReviewRule], rule_code: str) -> ReviewRule | None:
    """按规则编码取出规则配置；未配置返回 None，由调用方整体跳过该规则。"""
    # 步骤 1：线性匹配规则编码——rule_code 是程序内引用的稳定标识（PRD 12.3 G07）
    for rule in rules:
        if rule.rule_code == rule_code:
            return rule
    # 步骤 2：未命中即返回 None，交由调用方跳过；不在此处臆造阈值或默认配置
    return None


def params_of(rule: ReviewRule) -> dict[str, Any]:
    """取规则的参数表；未配置参数时返回空字典，由调用方按缺省规则处理。"""
    # 步骤 1：params_json 承载阈值、区间等具体取值（PRD 12.3 G07）
    return rule.params_json or {}


def as_decimal(value: Any) -> Decimal | None:
    """把 JSON 列中的数值转为 Decimal；为空或无法转换时返回 None（禁止 float，PRD 20.1 P1）。"""
    # 步骤 1：空值直接返回 None，交由调用方判定「数据不足」
    if value is None or value == "":
        return None
    # 步骤 2：已是 Decimal 则原样返回，避免二次转换损失精度
    if isinstance(value, Decimal):
        return value
    # 步骤 3：其余走字符串转换；转换失败返回 None 而不是抛错（配置可能写错）
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def as_date(value: Any) -> date | None:
    """把 JSON 列中的日期转为 date；为空或无法解析时返回 None。"""
    # 步骤 1：空值返回 None
    if not value:
        return None
    # 步骤 2：已是 date 则原样返回
    if isinstance(value, date):
        return value
    # 步骤 3：字符串按 ISO 日期解析（截取前 10 位以兼容带时间的取值）；失败返回 None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def to_text(value: Any) -> str:
    """把取值规整为可精确比对的文本：去首尾空白，None 归空串。"""
    # 步骤 1：空值归为空串，便于调用方直接做相等判定
    if value is None:
        return ""
    # 步骤 2：转文本并去首尾空白——只做精确比对，不做模糊或语义比对（语义比对属 A3 的 L8）
    return str(value).strip()


def decide_level(ratio: Decimal | None, params: dict[str, Any]) -> RiskLevel:
    """按规则参数判定单项风险等级（PRD 9.2 只规定等级取值，档位阈值由规则配置给出）。"""
    # 步骤 1：优先按偏离比例分档——达到 high_ratio 判 high，达到 medium_ratio 判 medium
    high = as_decimal(params.get(KEY_HIGH_RATIO))
    medium = as_decimal(params.get(KEY_MEDIUM_RATIO))
    if ratio is not None and high is not None and ratio >= high:
        return RiskLevel.HIGH
    if ratio is not None and medium is not None and ratio >= medium:
        return RiskLevel.MEDIUM
    # 步骤 2：无比例档位时取配置的固定等级，供二元命中型规则（黑名单、重复票据等）使用
    fixed = params.get(KEY_LEVEL)
    if isinstance(fixed, RiskLevel):
        return fixed
    if isinstance(fixed, str):
        for level in RiskLevel:
            if level.value == fixed:
                return level
    # 步骤 3：都未配置则取 PRD 9.2 的最低档 low（低风险＝存在轻微差异，通常不影响审批）
    return RiskLevel.LOW


def to_ratio_text(value: Decimal | None) -> str | None:
    """把偏离比例转为展示文本：统一保留固定小数位，避免输出超长的原始除法结果。

    精度本身 PRD 未规定，此处取 ``RATIO_DIGITS``；该值只影响展示，不参与阈值判定
    （判定用的是原始 ``Decimal``）。
    """
    # 步骤 1：空值保持为空，由调用方判定「未计算」
    if value is None:
        return None
    # 步骤 2：按固定小数位取整后转文本（round 对 Decimal 返回 Decimal，且不会因位数过多报错）
    return str(round(value, RATIO_DIGITS))


def build_result(rule: ReviewRule, risk_title: str, actual: dict, reference: dict | None = None,
                 evidence: dict | None = None, ratio: Decimal | None = None) -> dict:
    """按 PRD 9.3 组装一条命中结果；键名与 A3 消费的 ``rule_results`` 入参契约逐项对应。

    A3 的 ``step4_build_findings`` 读取 ``risk_type`` / ``risk_level`` / ``risk_title`` 与四个
    ``*_json`` 键，本函数的返回字典即为该契约；``description`` 与 ``suggestion_text`` 不在此产出——
    它们由 A3 的大模型环节（PRD 20.4 L9、L10）撰写，规则引擎只出事实与阈值。
    """
    # 步骤 1：取规则参数，用于等级判定与阈值展示
    params = params_of(rule)
    # 步骤 2：组装阈值展示——固定带 rule_id（PRD 9.3 的示例即为 {"tolerance": ..., "rule_id": ...}）
    threshold = {"rule_id": rule.rule_code, "rule_name": rule.rule_name}
    threshold.update(params)
    # 步骤 3：按偏离比例与配置档位判定单项等级（PRD 9.2）
    level = decide_level(ratio, params)
    # 步骤 4：返回结果字典——risk_type 用规则编码，便于按规则分类统计（PRD 6.2.8）
    return {"risk_type": rule.rule_code,
            "risk_level": level,
            "risk_title": risk_title,
            "actual_value_json": actual,          # 计算值（PRD 9.3）
            "reference_value_json": reference,    # 对比值（PRD 9.3）
            "threshold_json": threshold,          # 规则阈值（PRD 9.3）
            "evidence_json": evidence}            # 数据来源（PRD 9.3）
