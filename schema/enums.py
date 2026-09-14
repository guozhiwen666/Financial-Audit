"""状态与等级枚举。

只收录 PRD 中**明确列举了取值**的枚举（2.7.2 单据类型、2.7.12 各状态与等级、
2.7.13 处理建议）。PRD 未列举取值的字段（如 ``users.status``、``session_status``、
``approval_mode``、``item_type``、``action_type`` 等）在表结构中保持 ``str``，不在此臆造。
"""

from enum import Enum  # Enum：枚举基类，用于声明取值封闭的状态与等级

__all__ = [
    "DocumentType",              # 单据类型
    "DocumentStatus",            # 单据状态
    "ApprovalInstanceStatus",    # 审批实例状态
    "ApprovalTaskStatus",        # 审批任务状态
    "AttachmentStorageStatus",   # 附件存储状态
    "AttachmentParseStatus",     # 附件解析状态
    "AnalysisTaskStatus",        # 分析任务状态
    "RiskLevel",                 # 风险等级
    "RiskReviewStatus",          # 风险项复核状态
    "Recommendation",            # 处理建议
]


class DocumentType(str, Enum):
    """单据类型（PRD 2.7.2 五类主要单据）。"""

    PUBLIC_PAYMENT = "对公付款单"                 # 对公付款单：向供应商/合作方支付的对公款项
    ADVANCE_PAYMENT = "预付款单"                  # 预付款单：合同签订后先行支付的预付性质款项
    BATCH_PAYMENT = "批量付款单"                  # 批量付款单：一次提交、多笔收款对象的付款
    EXPENSE_REIMBURSEMENT = "费用报销单"          # 费用报销单：日常费用发生后的报销申请
    TRAVEL_REIMBURSEMENT = "差旅报销单"           # 差旅报销单：出差产生的交通/住宿/餐费/补贴报销


class DocumentStatus(str, Enum):
    """单据状态（PRD 2.7.12）。"""

    DRAFT = "draft"                               # 草稿：尚未提交，申请人可自由编辑
    PENDING_REVIEW = "pending_review"             # 待审批：已提交，等待审批人员受理
    REVIEWING = "reviewing"                       # 审批中：审批人员已开始处理
    RETURNED = "returned"                         # 已退回：被退回，可修改后重新提交
    APPROVED = "approved"                         # 已通过：全部审批节点通过（终态）
    REJECTED = "rejected"                         # 已驳回：审批不通过（终态）
    WITHDRAWN = "withdrawn"                       # 已撤回：申请人撤回尚未处理的单据
    VOIDED = "voided"                             # 已作废：单据作废（终态）


class ApprovalInstanceStatus(str, Enum):
    """审批实例状态（PRD 2.7.12）。"""

    PENDING = "pending"                           # 待启动：实例已创建但尚未进入节点流转
    RUNNING = "running"                           # 流转中：正在按节点顺序审批
    APPROVED = "approved"                         # 已通过：全部节点完成审批
    RETURNED = "returned"                         # 已退回：被某个节点退回
    REJECTED = "rejected"                         # 已驳回：被某个节点驳回
    CANCELLED = "cancelled"                       # 已取消：实例被取消，不再流转


class ApprovalTaskStatus(str, Enum):
    """审批任务状态（PRD 2.7.12）。"""

    PENDING = "pending"                           # 待处理：任务已生成，等待审批人处理
    APPROVED = "approved"                         # 已通过：该节点审批通过
    RETURNED = "returned"                         # 已退回：该节点退回给申请人修改
    REJECTED = "rejected"                         # 已驳回：该节点驳回单据
    CANCELLED = "cancelled"                       # 已取消：任务随实例取消而失效


class AttachmentStorageStatus(str, Enum):
    """附件存储状态（PRD 2.7.12）。"""

    UPLOADING = "uploading"                       # 上传中：文件尚未写入存储
    STORED = "stored"                             # 已存储：文件已成功保存
    FAILED = "failed"                             # 存储失败：文件未能保存成功


class AttachmentParseStatus(str, Enum):
    """附件解析状态（PRD 2.7.12）。"""

    PENDING = "pending"                           # 待解析：已存储，尚未开始解析
    PARSING = "parsing"                           # 解析中：正在执行 OCR / 文本提取
    SUCCEEDED = "succeeded"                       # 解析成功：文本与字段均已提取
    FAILED = "failed"                             # 解析失败：解析未产出结果
    MANUAL_REVIEW = "manual_review"               # 待人工复核：解析结果置信度低需人工确认


class AnalysisTaskStatus(str, Enum):
    """分析任务状态（PRD 2.7.12）。"""

    QUEUED = "queued"                             # 排队中：任务已创建，等待执行
    QUERYING_DOCUMENT = "querying_document"       # 查询单据：正在读取单据字段与明细
    LOADING_ATTACHMENTS = "loading_attachments"   # 加载附件：正在读取附件内容
    PARSING_ATTACHMENTS = "parsing_attachments"   # 解析附件：正在提取附件关键字段
    ANALYZING = "analyzing"                       # 分析中：正在执行规则校验与风险判定
    SUCCEEDED = "succeeded"                       # 分析成功：已产出风险结论与报告
    FAILED = "failed"                             # 分析失败：中途出错未产出结论
    CANCELLED = "cancelled"                       # 已取消：任务被取消


class RiskLevel(str, Enum):
    """风险等级（PRD 2.7.7）。"""

    LOW = "low"                                   # 低风险：存在轻微差异，通常不影响审批
    MEDIUM = "medium"                             # 中风险：需要审批人重点关注或补充说明
    HIGH = "high"                                 # 高风险：可能造成资金损失，建议人工复核


class RiskReviewStatus(str, Enum):
    """风险项复核状态（PRD 2.7.12）。"""

    PENDING = "pending"                           # 待复核：尚未有人对该风险项作出判断
    CONFIRMED = "confirmed"                       # 已确认：人工确认该风险成立
    DISMISSED = "dismissed"                       # 已否定：人工判定该风险不成立


class Recommendation(str, Enum):
    """处理建议（PRD 2.7.13）。"""

    APPROVE = "建议通过"                          # 建议通过：未发现实质问题，可审批通过
    SUPPLEMENT = "补充材料"                       # 补充材料：信息或附件不足，需申请人补齐
    MANUAL_REVIEW = "人工复核"                    # 人工复核：风险需审批人人工判断
    REJECT = "建议驳回"                           # 建议驳回：存在严重问题，建议驳回单据
