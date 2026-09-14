"""实时消息结构（PRD 2.7.12）。

字段与 PRD 列举逐项一致。消息为事件载荷，字段全部必填，不设默认值。
"""

from dataclasses import dataclass        # dataclass：声明纯字段结构，不引入任何行为
from datetime import datetime            # datetime：done 消息的完成时间

from schema.enums import (
    AnalysisTaskStatus,                  # 分析任务状态：task_status 消息用
    ApprovalTaskStatus,                  # 审批任务状态：approval_status 消息用
    AttachmentParseStatus,               # 附件解析状态：attachment_status 消息用
    AttachmentStorageStatus,             # 附件存储状态：attachment_status 消息用
    DocumentStatus,                      # 单据状态：document_status 消息用
    RiskLevel,                           # 风险等级：risk_finding / report_ready 消息用
)

__all__ = [
    "DocumentStatusMessage",     # 单据状态变化消息
    "ApprovalStatusMessage",     # 审批状态变化消息
    "SlotRequiredMessage",       # 槽位补全请求消息
    "TaskStatusMessage",         # 分析任务进度消息
    "AttachmentStatusMessage",   # 附件状态变化消息
    "RiskFindingMessage",        # 单条风险项产出消息
    "ReportReadyMessage",        # 报告就绪消息
    "ErrorMessage",              # 失败消息
    "DoneMessage",               # 任务结束消息
]


@dataclass
class DocumentStatusMessage:
    """document_status 消息：单据状态或版本发生变化时推送。"""

    document_id: int                             # 单据主键，定位是哪一张单据
    document_status: DocumentStatus              # 单据当前状态（如提交后变为待审批）
    current_version: int                          # 当前版本号，版本变化时申请人需注意重提


@dataclass
class ApprovalStatusMessage:
    """approval_status 消息：审批节点或任务状态变化时推送。"""

    document_id: int                             # 单据主键，便于前端刷新对应单据
    instance_id: int                             # 审批实例主键，标识本次审批流转
    node_id: int                                 # 当前审批节点主键，标识流转到哪个节点
    task_status: ApprovalTaskStatus              # 该节点任务的状态（通过/退回/驳回等）


@dataclass
class SlotRequiredMessage:
    """slot_required 消息：多轮交互中请求申请人补齐缺失信息。"""

    session_id: int                              # 审核会话主键，标识在哪个会话中提问
    slot_name: str                               # 待补齐的槽位名（如单据类型、单据编号）
    question_text: str                           # 向用户展示的追问文案
    candidate_values: list[str]                  # 候选值列表，存在歧义时供用户选择确认


@dataclass
class TaskStatusMessage:
    """task_status 消息：分析任务的分步骤进度推送。"""

    task_id: int                                 # 分析任务主键
    task_status: AnalysisTaskStatus              # 任务当前状态（如分析中、已完成）
    current_step: str                            # 当前执行步骤，用于展示进度说明
    progress: int                                # 进度百分比 0~100，用于渲染进度条


@dataclass
class AttachmentStatusMessage:
    """attachment_status 消息：附件存储或解析状态变化时推送。"""

    attachment_id: int                           # 附件主键
    storage_status: AttachmentStorageStatus      # 存储状态（上传中/已存储/失败）
    parse_status: AttachmentParseStatus          # 解析状态（待解析/成功/失败等）


@dataclass
class RiskFindingMessage:
    """risk_finding 消息：每产出一条风险结论即推送一条。"""

    task_id: int                                 # 所属分析任务主键
    finding_id: int                              # 风险项主键，便于逐条查看与复核
    risk_type: str                               # 风险类型（对应风险规则的分类）
    risk_level: RiskLevel                        # 该风险项的风险等级
    risk_title: str                              # 风险标题，用于列表快速识别


@dataclass
class ReportReadyMessage:
    """report_ready 消息：风险报告生成完毕可查看。"""

    task_id: int                                 # 所属分析任务主键
    report_id: int                               # 报告主键，用于拉取报告详情
    overall_risk_level: RiskLevel                # 整体风险等级（取最高单项并结合数量）


@dataclass
class ErrorMessage:
    """error 消息：查询、加载、解析或分析失败时推送。"""

    task_id: int                                 # 关联任务主键，标识出错的任务
    error_code: str                               # 错误码，供前端区分失败类型
    error_message: str                            # 错误说明，用于展示失败环节


@dataclass
class DoneMessage:
    """done 消息：任务流程结束（无论成功与否）时推送。"""

    task_id: int                                 # 关联任务主键
    finished_at: datetime                        # 结束时间，用于展示耗时与排序
