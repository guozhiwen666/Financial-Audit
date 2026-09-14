"""接口序列化：把领域实体转为可 JSON 化的字典（PRD 13 章统一响应）。

约定：枚举取取值字符串、Decimal 转字符串（保留精度，避免浮点误差）、
时间转 ISO 8601（PRD 12.2 时间戳统一 UTC 存储）。
"""

import datetime  # 时间序列化
from dataclasses import fields, is_dataclass  # 实体字段遍历
from decimal import Decimal  # 金额序列化
from enum import Enum  # 枚举序列化

__all__ = ["as_dict", "as_list"]

# 绝不外泄的字段：密码哈希等凭据类字段（PRD 16 安全边界：密码必须安全哈希保存且不外露）
_SENSITIVE = {"password_hash"}


def _value(value):
    """递归转换单个取值。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    # 金额一律转字符串：JSON 数字无法保证定点精度（PRD 9.3 取值示例亦为字符串）
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if is_dataclass(value):
        return as_dict(value)
    if isinstance(value, dict):
        return {key: _value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_value(item) for item in value]
    return str(value)


def as_dict(entity) -> dict | None:
    """实体 → 字典；入参为 None 时返回 None；凭据类字段一律不外泄。

    非 dataclass 与 dict 的取值（如枚举、金额、时间）直接按其取值序列化，
    便于接口把「整体风险等级」这类标量一并走同一序列化入口。
    """
    if entity is None:
        return None
    if isinstance(entity, dict):
        return {key: _value(item) for key, item in entity.items() if key not in _SENSITIVE}
    if is_dataclass(entity):
        return {name: _value(getattr(entity, name)) for name in (f.name for f in fields(entity))
                if name not in _SENSITIVE}
    return _value(entity)


def as_list(items) -> list:
    """实体列表 → 字典列表。"""
    return [as_dict(item) for item in (items or [])]
