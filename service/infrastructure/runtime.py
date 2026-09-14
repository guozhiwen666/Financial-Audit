"""运行期装配：主流程单例、实时消息出口与留痕落库（PRD 2.7.1、14.2、14.3、20.3）。

职责：把最外层主流程（``flow.MainFlow``）装配为进程内单例，并负责把各环节在内存中累积的
产出（实时消息、状态留痕、审计留痕）落到数据库——环节本身只产出实体，落库由服务层负责。

边界：本模块不做业务判断，只做装配、缓冲与落库搬运。
"""

from agent.utils.llm import LLMClient  # 大模型调用封装（PRD 20.4）
from agent.utils.message import MessagePublisher  # 实时消息构造与推送（PRD 14.2）
from config.config import llm_config  # 模型配置（config/config.py）
from flow.main_flow import MainFlow  # 最外层主流程（PRD 7.1 / 8.1 两张 LangGraph 图）
from service.infrastructure import repository as repo

__all__ = ["flow", "publisher", "messages_since", "flush_audit_logs", "flush_status_logs"]

_flow: MainFlow | None = None  # 主流程单例：图编译有成本，进程内复用


def flow() -> MainFlow:
    """返回主流程单例；首次调用时按配置装配（PRD 2.7.1 最外层主流程）。"""
    # 步骤 1：懒加载——避免导入本模块即触发大模型客户端与两张图的构造
    global _flow
    if _flow is None:
        _flow = MainFlow(LLMClient(llm_config.llm_model), MessagePublisher())
    return _flow


def publisher() -> MessagePublisher:
    """返回主流程使用的消息推送器（PRD 14.2 九类实时消息）。"""
    return flow().orchestrator.publisher


def messages_since(seq: int) -> list[dict]:
    """取出序号大于 ``seq`` 的实时消息，供前端轮询增量拉取（PRD 14.3 可去重、可乱序重排）。"""
    # 步骤 1：按序号过滤，前端凭 seq 自行去重
    return [message for message in publisher().messages if message["seq"] > seq]


def flush_audit_logs() -> int:
    """把审计环节累积的留痕落库，返回落库条数（PRD 2.7.14 操作必须留痕）。

    留痕只追加、不改写（PRD 20.1 P7）；落库后回填主键并清空缓冲，避免重复写入。
    """
    # 步骤 1：取缓冲区；无新增时直接返回 0，不产生空事务
    entries = flow().audit_log.audit_logs
    if not entries:
        return 0
    # 步骤 2：逐条落库并回填主键
    for entry in entries:
        entry.id = repo.audit_logs.insert(entry)
    # 步骤 3：清空缓冲——留痕已在库中，缓冲区仅作暂存
    count = len(entries)
    entries.clear()
    return count


def flush_status_logs() -> int:
    """把单据状态留痕落库，返回落库条数（PRD 7.2 保存状态变化、7.3 流转留痕）。

    环节一（提交/撤回/作废）与环节三（审批结论）各自累积留痕，故两处缓冲一并处理。
    """
    # 步骤 1：合并两处缓冲
    created = flow().document_creation.status_logs
    approved = flow().approval.status_logs
    entries = created + approved
    if not entries:
        return 0
    # 步骤 2：逐条落库并回填主键
    for entry in entries:
        entry.id = repo.document_status_logs.insert(entry)
    # 步骤 3：清空缓冲区
    created.clear()
    approved.clear()
    return len(entries)
