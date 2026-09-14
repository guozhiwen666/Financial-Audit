"""取值转换：把解析结果中的文本取值转为实体字段类型（PRD 5.4 字段提取结果的归档）。

背景：A2 抽取出的是文本（如 ``"¥1,200.00"``、``"2026年8月15日"``），落库前须转为
``Decimal`` / ``date``。无法解析时一律返回 None，**不静默置零**——审计场景中「有值但解析成空」
必须可见（PRD 16 所有结论须保留数据来源）。
"""

import datetime  # 日期解析
from decimal import Decimal, InvalidOperation  # 金额精确解析

__all__ = ["to_decimal", "to_date"]


def to_decimal(value) -> Decimal | None:
    """把文本金额转为 Decimal；支持千分位与常见货币符号前缀，无法解析时返回 None。"""
    # 步骤 1：空值直接返回 None
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    # 步骤 2：剥离常见货币符号、千分位与空白后解析
    text = str(value)
    for symbol in ("¥", "￥", "$", ",", " ", "元"):
        text = text.replace(symbol, "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def to_date(value) -> datetime.date | None:
    """把文本日期转为 date；支持 2026-08-15 / 2026/08/15 / 2026年8月15日 等写法。"""
    # 步骤 1：已是日期类型时原样返回
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    # 步骤 2：统一替换中文年月日后按常见格式尝试解析
    text = str(value).strip().replace("年", "-").replace("月", "-").replace("日", "")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
