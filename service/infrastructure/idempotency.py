"""幂等控制（PRD 11.1 幂等性、13.10 Idempotency-Key）。

PRD 11.1 要求提交、解析、分析、审批动作支持幂等键，防止重复提交产生重复任务或重复审批；
PRD 13.10 要求写操作统一携带 ``Idempotency-Key`` 请求头。

实现说明：本项目为单进程部署，故用进程内映射缓存「幂等键 → 首次执行结果」；
多进程或多实例部署时应替换为共享存储（如数据库表或 Redis）。
"""

from collections import OrderedDict  # 有界缓存：超限时淘汰最早的键
from typing import Callable  # 动作签名

__all__ = ["run_once", "MAX_ENTRIES"]

MAX_ENTRIES = 1024  # 缓存上限：避免长期运行后无限增长
_results: "OrderedDict[str, object]" = OrderedDict()


def run_once(key: str | None, scope: str, action: Callable):
    """按幂等键执行动作：键重复时直接复用上次结果（PRD 11.1 防止重复任务与重复审批）。

    ``scope`` 用于把键隔离到具体资源（如同一幂等键作用于不同单据不算重复）。
    未传幂等键时不做缓存，直接执行——是否强制由接口层决定（PRD 13.10）。
    """
    # 步骤 1：无幂等键直接执行，不引入任何额外状态
    if not key:
        return action()
    composite = "%s:%s" % (scope, key)
    # 步骤 2：命中缓存即复用首次结果，不再重复执行
    if composite in _results:
        return _results[composite]
    # 步骤 3：首次执行并缓存结果；超限时淘汰最早的一条
    result = action()
    _results[composite] = result
    while len(_results) > MAX_ENTRIES:
        _results.popitem(last=False)
    return result
