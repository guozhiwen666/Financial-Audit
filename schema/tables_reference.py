"""参考数据与操作审计表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

__all__ = ["MarketPriceReference", "SupplierProfile", "AuditLog"]


@dataclass
class MarketPriceReference:
    """market_price_references 表：市场价参考区间（风险规则 R06 的数据来源）。"""

    id: int
    item_name: str | None = None
    specification: str | None = None
    region: str | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    currency: str | None = None
    source_name: str | None = None
    effective_date: date | None = None


@dataclass
class SupplierProfile:
    """supplier_profiles 表：供应商档案与风险标签（风险规则 R08 的数据来源）。"""

    id: int
    supplier_code: str | None = None
    supplier_name: str | None = None
    credit_status: str | None = None
    blacklist_status: str | None = None
    risk_tags_json: dict[str, Any] | None = None
    bank_accounts_json: dict[str, Any] | None = None
    updated_at: datetime | None = None


@dataclass
class AuditLog:
    """audit_logs 表：操作审计记录。"""

    id: int
    user_id: int | None = None
    action_type: str | None = None
    resource_type: str | None = None
    resource_id: int | None = None
    detail_json: dict[str, Any] | None = None
    created_at: datetime | None = None
