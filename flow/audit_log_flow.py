"""环节七 操作审计（PRD 2.7.1 操作审计、2.7.14）。

PRD 2.7.9 的「日志模块」负责接口调用、附件访问、规则变更、分析任务与审批操作的审计；
PRD 2.7.14 要求审批结果、风险项处理与规则变更必须记录操作人、操作时间和变更内容。
PRD 20.1 P7 进一步要求留痕**只可追加**，不得修改或删除，故本环节只维护一个只增的列表。

本环节不依赖其他环节，被环节一、环节三、环节五复用。
"""

from datetime import datetime, timezone  # 审计时间戳（PRD 12.2：时间戳统一 UTC 存储）

from schema.tables_reference import AuditLog  # 操作审计留痕表（PRD 2.7.10）

__all__ = ["AuditLogFlow"]


class AuditLogFlow:
    """环节七 操作审计（PRD 2.7.1、2.7.14）。"""

    def __init__(self) -> None:
        """初始化只增的审计留痕容器。"""
        self.audit_logs: list[AuditLog] = []  # 审计记录只可追加，不可修改或删除（PRD 20.1 P7）

    def record(self, action_type: str, resource_type: str, resource_id: int,
               user_id: int | None = None, detail: dict | None = None) -> AuditLog:
        """记录操作审计：接口调用、附件访问、规则变更、分析任务与审批操作（PRD 2.7.9 日志模块）。"""
        # 步骤 1：构造审计实体；主键待落库后回填，故以 0 占位（schema 约定主键必填）
        #         操作人、操作时间与变更内容三者必须齐备（PRD 2.7.14），user_id 为空表示系统动作
        entry = AuditLog(id=0,
                         user_id=user_id,                # 操作人：None 表示系统自动动作
                         action_type=action_type,        # 动作类型：审批 / 复核 / 分析任务等
                         resource_type=resource_type,    # 资源类型：被操作的数据库表名
                         resource_id=resource_id,        # 资源主键：被操作的具体记录
                         detail_json=detail,             # 变更内容：本次操作涉及的字段与取值
                         created_at=datetime.now(timezone.utc))  # 操作时间：统一 UTC
        # 步骤 2：追加到留痕列表——只增不改，保证审计链可追溯（PRD 20.1 P7）
        self.audit_logs.append(entry)
        # 步骤 3：返回该条留痕，供调用方落库
        return entry
