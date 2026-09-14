"""数据仓储：按 dataclass 字段自动完成实体与数据行的双向映射（PRD 11 章各后端模块的公共依赖）。

约定（对齐 schema/ 的既有约定）：实体一律是 ``schema/`` 中的 dataclass，本模块不新增任何数据结构；
列名与字段名严格同名，故无需映射表，避免「两套命名各自为政」。
类型转换集中在本模块：枚举 ↔ 取值字符串、JSON 列 ↔ dict/list、时间戳 ↔ datetime、布尔 ↔ 0/1。
"""

import datetime  # 时间戳/日期列的还原
import json  # JSON 列的读写
from dataclasses import fields
from decimal import Decimal  # 金额列的精确还原
from enum import Enum  # 枚举列的还原
from typing import Any, get_args, get_origin, get_type_hints

from schema.tables_analysis import AnalysisTask, ManualReview, ReviewReport, RiskFinding
from schema.tables_approval import (ApprovalInstance, ApprovalTask, ApprovalWorkflow,
                                    ApprovalWorkflowNode, DocumentStatusLog)
from schema.tables_auth import Permission, Role, RolePermission, User, UserRole
from schema.tables_document import (AttachmentParseResult, DocumentAttachment, DocumentLineItem,
                                    DocumentVersion, FinancialDocument, InvoiceRecord)
from schema.tables_reference import AuditLog, MarketPriceReference, SupplierProfile
from schema.tables_rules import ExpenseStandard, ReviewRule
from schema.tables_session import ReviewSession, SessionMessage, SessionSlot
from service.infrastructure.database import execute, query, query_one

__all__ = [
    "BaseRepo", "users", "roles", "permissions", "user_roles", "role_permissions",
    "review_sessions", "session_messages", "session_slots", "financial_documents",
    "document_versions", "document_line_items", "document_attachments",
    "attachment_parse_results", "invoice_records", "approval_workflows",
    "approval_workflow_nodes", "approval_instances", "approval_tasks", "document_status_logs",
    "analysis_tasks", "risk_findings", "review_reports", "manual_reviews", "review_rules",
    "expense_standards", "market_price_references", "supplier_profiles", "audit_logs", "TABLES",
]


def _unwrap(hint: Any) -> Any:
    """解包 ``X | None``，取真实类型。"""
    if get_origin(hint) is not None:
        args = [a for a in get_args(hint) if a is not type(None)]
        return args[0] if args else str
    return hint


class BaseRepo:
    """单表仓储：按 dataclass 字段自动生成列清单，提供基础读写。"""

    def __init__(self, table: str, model: type) -> None:
        self.table = table
        self.model = model
        self.columns = [f.name for f in fields(model)]
        self.hints = get_type_hints(model)

    @staticmethod
    def to_db(value: Any) -> Any:
        """实体值 → 数据库参数：枚举取取值、布尔转 0/1、dict/list 序列化为 JSON。"""
        if value is None:
            return None
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)
        return value

    def from_db(self, name: str, value: Any) -> Any:
        """数据库列值 → 实体值：按字段类型注解还原（金额保精度、时间还原为 date/datetime）。"""
        if value is None:
            return None
        base = _unwrap(self.hints[name])
        # 步骤 1：枚举与布尔
        if isinstance(base, type) and issubclass(base, Enum):
            return base(value)
        if base is bool:
            return bool(value)
        # 步骤 2：金额保精度（先转字符串再转 Decimal，避免二进制浮点误差）
        if base is Decimal:
            return Decimal(str(value))
        # 步骤 3：时间——datetime 是 date 的子类，须先判 datetime
        if base is datetime.datetime:
            return (value if isinstance(value, datetime.datetime)
                    else datetime.datetime.fromisoformat(str(value)))
        if base is datetime.date:
            if isinstance(value, datetime.datetime):
                return value.date()
            return (value if isinstance(value, datetime.date)
                    else datetime.date.fromisoformat(str(value)))
        # 步骤 4：JSON 列
        if base is dict or base is list or get_origin(base) in (dict, list):
            return json.loads(value) if isinstance(value, str) else value
        # 步骤 5：基础标量
        if base is int:
            return int(value)
        if base is float:
            return float(value)
        if base is str:
            return str(value)
        return value

    def to_model(self, row: dict) -> Any:
        """数据行 → 实体。"""
        return self.model(**{name: self.from_db(name, row.get(name)) for name in self.columns})

    def coerce(self, name: str, value: Any) -> Any:
        """接口传入的 JSON 值 → 实体字段值（金额转 Decimal、日期串转 date、枚举串转枚举）。"""
        if value is None:
            return None
        base = _unwrap(self.hints[name])
        # 步骤 1：结构化值（JSON 列）原样保留
        if isinstance(base, dict) or isinstance(base, list):
            return value
        # 步骤 2：枚举取取值字符串
        if isinstance(base, type) and issubclass(base, Enum):
            return base(value)
        if base is bool:
            return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")
        # 步骤 3：金额必须经字符串转 Decimal，避免二进制浮点误差（PRD 12.2 金额用定点数）
        if base is Decimal:
            return Decimal(str(value))
        # 步骤 4：时间——接口统一传 ISO 8601 字符串
        if base is datetime.datetime:
            return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if base is datetime.date:
            return datetime.date.fromisoformat(str(value)[:10])
        # 步骤 5：基础标量
        if base is int:
            return int(value)
        if base is float:
            return float(value)
        return str(value)

    def insert(self, entity: Any) -> int:
        """插入实体（主键由数据库生成），返回新主键。"""
        # 步骤 1：主键交由数据库自增，不参与插入
        names = [c for c in self.columns if c != "id"]
        placeholders = ", ".join(["%s"] * len(names))
        sql = "INSERT INTO %s (%s) VALUES (%s)" % (self.table, ", ".join(names), placeholders)
        # 步骤 2：按列顺序取值并转换后执行
        return execute(sql, [self.to_db(getattr(entity, n)) for n in names])

    def get(self, primary_key: int) -> Any:
        """按主键取实体，不存在时返回 None。"""
        row = query_one("SELECT * FROM %s WHERE id = %%s" % self.table, (primary_key,))
        return self.to_model(row) if row else None

    def find(self, where: str = "", params: tuple | list = (), order: str = "",
             limit: int | None = None, offset: int | None = None) -> list:
        """条件查询实体列表；where 用占位符 ``%s`` 传参（PRD 16 禁止拼接值）。"""
        # 步骤 1：拼装 SQL 骨架，条件片段均为代码内常量，值一律走占位符
        sql = "SELECT * FROM %s" % self.table
        if where:
            sql += " WHERE " + where
        if order:
            sql += " ORDER BY " + order
        # 步骤 2：分页（PRD 13.10 列表接口统一分页）
        if limit is not None:
            sql += " LIMIT %d" % int(limit)
            if offset:
                sql += " OFFSET %d" % int(offset)
        return [self.to_model(row) for row in query(sql, params)]

    def count(self, where: str = "", params: tuple | list = ()) -> int:
        """统计满足条件的行数（分页接口返回 total）。"""
        sql = "SELECT COUNT(*) AS total FROM %s" % self.table
        if where:
            sql += " WHERE " + where
        return int(query_one(sql, params)["total"])

    def update(self, primary_key: int, **values: Any) -> int:
        """按主键更新指定列，返回受影响行数。"""
        # 步骤 1：只允许更新真实存在的列，避免拼出非法 SQL
        unknown = set(values) - set(self.columns)
        if unknown:
            raise ValueError("非法的列名：%s" % ", ".join(sorted(unknown)))
        if not values:
            return 0
        # 步骤 2：参数化更新
        assignments = ", ".join("%s = %%s" % name for name in values)
        sql = "UPDATE %s SET %s WHERE id = %%s" % (self.table, assignments)
        return execute(sql, [self.to_db(v) for v in values.values()] + [primary_key])

    def delete(self, primary_key: int) -> int:
        """按主键删除，返回受影响行数。"""
        return execute("DELETE FROM %s WHERE id = %%s" % self.table, (primary_key,))


# 各表仓储实例：表名与 schema/ 中的 dataclass 一一对应
users = BaseRepo("users", User)                                    # 用户
roles = BaseRepo("roles", Role)                                    # 角色
permissions = BaseRepo("permissions", Permission)                  # 权限点
user_roles = BaseRepo("user_roles", UserRole)                      # 用户-角色关联
role_permissions = BaseRepo("role_permissions", RolePermission)    # 角色-权限关联
review_sessions = BaseRepo("review_sessions", ReviewSession)       # 审核会话
session_messages = BaseRepo("session_messages", SessionMessage)    # 会话消息
session_slots = BaseRepo("session_slots", SessionSlot)             # 会话槽位状态
financial_documents = BaseRepo("financial_documents", FinancialDocument)      # 单据主表
document_versions = BaseRepo("document_versions", DocumentVersion)            # 单据版本快照
document_line_items = BaseRepo("document_line_items", DocumentLineItem)       # 单据明细行
document_attachments = BaseRepo("document_attachments", DocumentAttachment)   # 附件
attachment_parse_results = BaseRepo("attachment_parse_results", AttachmentParseResult)  # 解析结果
invoice_records = BaseRepo("invoice_records", InvoiceRecord)                  # 发票记录
approval_workflows = BaseRepo("approval_workflows", ApprovalWorkflow)         # 审批流程定义
approval_workflow_nodes = BaseRepo("approval_workflow_nodes", ApprovalWorkflowNode)  # 流程节点
approval_instances = BaseRepo("approval_instances", ApprovalInstance)         # 审批实例
approval_tasks = BaseRepo("approval_tasks", ApprovalTask)                     # 审批任务
document_status_logs = BaseRepo("document_status_logs", DocumentStatusLog)    # 单据状态留痕
analysis_tasks = BaseRepo("analysis_tasks", AnalysisTask)                     # 分析任务
risk_findings = BaseRepo("risk_findings", RiskFinding)                        # 风险项
review_reports = BaseRepo("review_reports", ReviewReport)                     # 风险审核报告
manual_reviews = BaseRepo("manual_reviews", ManualReview)                     # 人工复核记录
review_rules = BaseRepo("review_rules", ReviewRule)                           # 审核规则
expense_standards = BaseRepo("expense_standards", ExpenseStandard)            # 费用标准
market_price_references = BaseRepo("market_price_references", MarketPriceReference)  # 市场价参考
supplier_profiles = BaseRepo("supplier_profiles", SupplierProfile)            # 供应商档案
audit_logs = BaseRepo("audit_logs", AuditLog)                                 # 操作审计日志

# 表名 → 仓储，供按表名统一取用（如日志、通用查询）
TABLES = {
    repo.table: repo for repo in (
        users, roles, permissions, user_roles, role_permissions, review_sessions, session_messages,
        session_slots, financial_documents, document_versions, document_line_items,
        document_attachments, attachment_parse_results, invoice_records, approval_workflows,
        approval_workflow_nodes, approval_instances, approval_tasks, document_status_logs,
        analysis_tasks, risk_findings, review_reports, manual_reviews, review_rules,
        expense_standards, market_price_references, supplier_profiles, audit_logs,
    )
}
