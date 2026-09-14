"""参考数据与操作审计表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
"""

from dataclasses import dataclass        # dataclass：声明纯字段结构
from datetime import date, datetime      # date：生效日期；datetime：更新时间与操作时间
from decimal import Decimal              # Decimal：价格区间，禁止 float
from typing import Any                   # Any：JSON 列内的值类型不固定

__all__ = [
    "MarketPriceReference",    # 市场价参考表
    "SupplierProfile",         # 供应商档案表
    "AuditLog",                # 操作审计日志表
]


@dataclass
class MarketPriceReference:
    """market_price_references 表：市场价参考区间（风险规则 R06 的数据来源）。"""

    id: int                                       # 主键
    item_name: str | None = None                  # 商品或服务名称
    specification: str | None = None              # 规格型号，可与名称组合匹配
    region: str | None = None                     # 适用地区
    price_min: Decimal | None = None              # 参考价下限
    price_max: Decimal | None = None              # 参考价上限
    currency: str | None = None                   # 币种（PRD 未列举取值，保持字符串）
    source_name: str | None = None                # 数据来源名称，结论需标注来源
    effective_date: date | None = None            # 生效日期，用于判断参考价是否过期


@dataclass
class SupplierProfile:
    """supplier_profiles 表：供应商档案与风险标签（风险规则 R08 的数据来源）。"""

    id: int                                               # 主键
    supplier_code: str | None = None                      # 供应商编码
    supplier_name: str | None = None                      # 供应商名称
    credit_status: str | None = None                      # 资质状态（取值 PRD 未列举，保持字符串）
    blacklist_status: str | None = None                   # 黑名单状态（取值 PRD 未列举，保持字符串）
    risk_tags_json: dict[str, Any] | None = None          # 风险标签集合
    bank_accounts_json: dict[str, Any] | None = None      # 收款账号集合，用于识别账号变更
    updated_at: datetime | None = None                    # 最近一次更新时间


@dataclass
class AuditLog:
    """audit_logs 表：操作审计记录（审批、附件访问、规则变更等留痕）。"""

    id: int                                          # 主键
    user_id: int | None = None                       # 操作人用户主键，指向 users.id
    action_type: str | None = None                   # 操作类型（取值 PRD 未列举，保持字符串）
    resource_type: str | None = None                 # 被操作资源类型（单据/附件/规则等）
    resource_id: int | None = None                   # 被操作资源主键
    detail_json: dict[str, Any] | None = None        # 操作明细（变更内容等）
    created_at: datetime | None = None               # 操作时间
