"""单据状态流转表（PRD 7.3）。

PRD 7.3 以表格形式规定了单据在各状态下允许执行的动作与目标状态。本模块把该表落成
「当前状态 → 允许流转到的目标状态」的映射，供环节一（单据创建）与环节三（审批流转）**共用**：
该表是状态机的唯一真源，若在两处各写一份，迟早会各自漂移。

本模块只放数据表，不含任何操作。
"""

from schema.enums import DocumentStatus  # 单据状态枚举（PRD 2.7.12）

__all__ = ["ALLOWED_TRANSITIONS"]

# PRD 7.3 单据状态流转表：键为当前状态，值为允许流转到的目标状态；终态为空元组，不可再变更
ALLOWED_TRANSITIONS: dict[DocumentStatus, tuple[DocumentStatus, ...]] = {
    DocumentStatus.DRAFT: (DocumentStatus.PENDING_REVIEW,      # 提交
                           DocumentStatus.VOIDED),             # 作废
    DocumentStatus.PENDING_REVIEW: (DocumentStatus.WITHDRAWN,  # 撤回
                                    DocumentStatus.REVIEWING),  # 开始审批
    DocumentStatus.REVIEWING: (DocumentStatus.APPROVED,        # 末节点通过
                               DocumentStatus.RETURNED,        # 退回修改
                               DocumentStatus.REJECTED),       # 驳回（终态）
    DocumentStatus.RETURNED: (DocumentStatus.PENDING_REVIEW,   # 修改后重新提交
                              DocumentStatus.VOIDED),          # 作废
    DocumentStatus.WITHDRAWN: (DocumentStatus.PENDING_REVIEW,),  # 重新提交
    DocumentStatus.APPROVED: (),  # 终态：不可变更
    DocumentStatus.REJECTED: (),  # 终态：不可变更
    DocumentStatus.VOIDED: (),    # 终态：不可变更
}
