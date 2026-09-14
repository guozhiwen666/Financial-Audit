"""审核规则与费用标准表结构（PRD 12.3 G07、G08）。

新建原因：PRD 2.7.9 规则引擎需维护金额容差、费用标准、市场价区间与异常阈值，
2.7.11 已提供 ``/api/v1/rules`` 接口、2.7.13 报告需展示规则阈值，
但 2.7.10 的数据表清单中没有对应落点；风险规则 R05（费用标准合规性）同样缺数据来源。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空。
"""

from dataclasses import dataclass        # dataclass：声明纯字段结构
from datetime import date, datetime      # date：生效日期；datetime：更新时间戳
from decimal import Decimal              # Decimal：标准金额，禁止 float
from typing import Any                   # Any：JSON 列内的值类型不固定

__all__ = [
    "ReviewRule",        # 审核规则表（G07）
    "ExpenseStandard",   # 费用标准表（G08）
]


@dataclass
class ReviewRule:
    """review_rules 表 G07：审核规则配置。

    承载金额容差、费用标准、市场价区间、异常阈值等规则参数，
    供规则引擎执行校验、并在风险报告中标注所用阈值。
    """

    id: int                                         # 主键
    rule_code: str | None = None                    # 规则编码，程序内引用的稳定标识
    rule_name: str | None = None                    # 规则名称，展示用
    rule_type: str | None = None                    # 规则类型（金额容差/市场价区间/异常阈值等）
    params_json: dict[str, Any] | None = None       # 规则参数（阈值、区间等具体取值）
    status: str | None = None                       # 规则状态（启用/停用，取值 PRD 未列举）
    effective_date: date | None = None              # 生效日期，用于判断规则是否适用
    updated_by: int | None = None                   # 最近修改人，指向 users.id（规则变更需留痕）
    updated_at: datetime | None = None              # 最近修改时间


@dataclass
class ExpenseStandard:
    """expense_standards 表 G08：费用标准。

    风险规则 R05（费用标准合规性）的数据来源：按费用类别、部门、职级、地区
    与日期匹配适用的标准金额上限。
    """

    id: int                                        # 主键
    expense_category: str | None = None            # 费用类别，与单据费用类别匹配
    department: str | None = None                  # 适用部门
    job_level: str | None = None                   # 适用职级
    region: str | None = None                      # 适用地区
    standard_amount: Decimal | None = None         # 标准金额上限，超出即命中费用标准风险
    currency: str | None = None                    # 币种（PRD 未列举取值，保持字符串）
    effective_date: date | None = None             # 生效日期，用于判断标准是否适用
