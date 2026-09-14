"""单据模块（PRD 11 章「单据模块」、13.2、7.2、7.3）。

职责：单据创建、编辑、复制、查询、提交、撤回、作废、版本保存与状态流转。
边界：状态流转由环节一按 PRD 7.3 流转表强制执行；本模块只负责取数、权限拦截与落库，
不重复实现状态机，也不自行计算金额（合计校验在环节一内完成）。
"""

from schema.tables_document import FinancialDocument  # 单据实体
from service.infrastructure import repository as repo, runtime
from service.business_services import approval_service, auth_service
from service.infrastructure.database import transaction
from service.infrastructure.errors import BadRequest, NotFound, PermissionDenied

__all__ = ["EDITABLE_FIELDS", "create", "get", "require_document", "list_documents", "update",
           "copy_document", "submit", "withdraw", "void", "detail"]

# 可由接口直接写入的列：取数据表真实列并排除受保护列，避免自造字段（PRD 5.2 结构化字段）
_PROTECTED = {"id", "applicant_id", "document_status", "current_version",
              "created_at", "updated_at"}
EDITABLE_FIELDS = tuple(c for c in repo.financial_documents.columns if c not in _PROTECTED)


def require_document(document_id: int) -> FinancialDocument:
    """按主键取单据，不存在时抛 NotFound（PRD 13.10 统一错误响应）。"""
    document = repo.financial_documents.get(document_id)
    if document is None:
        raise NotFound("单据不存在：%s" % document_id)
    return document


def _apply_fields(document: FinancialDocument, payload: dict) -> FinancialDocument:
    """把请求体中的字段写入实体；出现数据表没有的字段即报错，杜绝静默丢数据。"""
    # 步骤 1：字段白名单校验——未列举的字段一律拒绝，而不是悄悄忽略
    unknown = set(payload) - set(EDITABLE_FIELDS)
    if unknown:
        raise BadRequest("不支持的字段：%s" % "、".join(sorted(unknown)))
    # 步骤 2：按字段类型转换后写入（金额转 Decimal、日期串转 date、枚举串转枚举）
    for name, value in payload.items():
        setattr(document, name, repo.financial_documents.coerce(name, value))
    return document


def _persist(document: FinancialDocument) -> int:
    """把单据的全部可编辑列写回数据库，返回受影响行数。"""
    values = {name: getattr(document, name) for name in EDITABLE_FIELDS}
    return repo.financial_documents.update(document.id, **values)


def create(applicant_id: int, department: str, payload: dict) -> FinancialDocument:
    """创建单据草稿（PRD 13.2 POST /documents、7.1-A）。"""
    # 步骤 1：单据类型必填，且必须是五类之一（PRD 5.1）——取值转换失败即报错
    if not payload.get("document_type"):
        raise BadRequest("缺少必填字段 document_type（PRD 5.2）")
    document_type = repo.financial_documents.coerce("document_type", payload["document_type"])
    # 步骤 2：交环节一构造草稿实体（初始化币种与 draft 状态）
    draft = runtime.flow().document_creation.create(document_type, applicant_id, department)
    # 步骤 3：写入请求体携带的其余字段
    _apply_fields(draft, {k: v for k, v in payload.items() if k != "document_type"})
    # 步骤 4：复用环节一的编辑校验（PRD 5.3 保存草稿即校验付款比例与出差日期）
    draft = runtime.flow().document_creation.update(draft)
    # 步骤 5：落库并回填主键
    draft.id = repo.financial_documents.insert(draft)
    runtime.flush_status_logs()
    return draft


def get(document_id: int) -> FinancialDocument | None:
    """按主键取单据（不校验权限，权限由调用方处理）。"""
    return repo.financial_documents.get(document_id)


def list_documents(role_codes: list[str], user_id: int, filters: dict, page: int,
                   page_size: int) -> tuple[list[FinancialDocument], int]:
    """按单据类型、申请人、部门、状态、日期查询单据列表（PRD 13.2 GET /documents）。"""
    where: list[str] = []
    params: list = []
    # 步骤 1：数据权限前置——在 SQL 层收敛可见范围，而非取回后内存过滤（PRD 11.1 权限前置）
    if not auth_service.can_view_all(role_codes):
        where.append("applicant_id = %s")
        params.append(user_id)
    # 步骤 2：逐项追加筛选条件，取值一律走占位符（PRD 16 禁止拼接）
    if filters.get("document_type"):
        where.append("document_type = %s")
        params.append(filters["document_type"])
    if filters.get("applicant_id"):
        where.append("applicant_id = %s")
        params.append(int(filters["applicant_id"]))
    if filters.get("department"):
        where.append("(applicant_department = %s OR budget_department = %s)")
        params += [filters["department"], filters["department"]]
    if filters.get("document_status"):
        where.append("document_status = %s")
        params.append(filters["document_status"])
    if filters.get("document_no"):
        where.append("document_no = %s")
        params.append(filters["document_no"])
    if filters.get("start_date"):
        where.append("apply_date >= %s")
        params.append(filters["start_date"])
    if filters.get("end_date"):
        where.append("apply_date <= %s")
        params.append(filters["end_date"])
    clause = " AND ".join(where)
    # 步骤 3：先取总数再取当页数据（PRD 13.10 列表接口统一分页并返回 total）
    total = repo.financial_documents.count(clause, params)
    rows = repo.financial_documents.find(clause, params, order="id DESC",
                                         limit=page_size, offset=(page - 1) * page_size)
    return rows, total


def update(document_id: int, payload: dict, role_codes: list[str],
           user_id: int) -> FinancialDocument:
    """编辑草稿或退回状态的单据（PRD 13.2 PATCH /documents/{document_id}）。"""
    # 步骤 1：取单据并校验编辑权限——申请人仅限本人单据（PRD 3.2、3.3）
    document = require_document(document_id)
    if not auth_service.can_edit_document(role_codes, user_id, document):
        raise PermissionDenied("仅申请人本人可编辑该单据")
    # 步骤 2：写入字段
    _apply_fields(document, payload)
    # 步骤 3：交环节一校验状态闸口与字段约束（PRD 7.3 仅 draft / returned 可编辑、5.3 字段校验）
    document = runtime.flow().document_creation.update(document)
    # 步骤 4：落库
    _persist(document)
    return document


def copy_document(document_id: int, role_codes: list[str], user_id: int) -> FinancialDocument:
    """复制单据并生成新草稿（PRD 13.2 POST /documents/{document_id}/copy）。"""
    # 步骤 1：取源单据并做可见性校验（PRD 3.3 数据权限）
    source = require_document(document_id)
    if not auth_service.can_view_document(role_codes, user_id, source):
        raise PermissionDenied("无权访问该单据")
    # 步骤 2：交环节一复制——主键、编号与版本重置，状态回到 draft（PRD 2.7.11）
    draft = runtime.flow().document_creation.copy(source)
    # 步骤 3：申请人改为当前操作人（复制出的新草稿归属操作者本人）
    draft.applicant_id = user_id
    # 步骤 4：落库；连同明细一并复制——否则复制出的单据内容不完整（PRD 2.7.11 复制单据）
    draft.id = repo.financial_documents.insert(draft)
    for item in repo.document_line_items.find("document_id = %s", (document_id,), order="id"):
        item.id = 0
        item.document_id = draft.id
        repo.document_line_items.insert(item)
    return draft


def submit(document_id: int, role_codes: list[str], user_id: int) -> dict:
    """提交单据并创建审批实例和分析任务（PRD 13.2 POST submit、7.2、11.1）。"""
    # 步骤 1：取单据并校验提交权限（申请人仅限本人单据，PRD 3.2）
    document = require_document(document_id)
    if not auth_service.can_edit_document(role_codes, user_id, document):
        raise PermissionDenied("仅申请人本人可提交该单据")
    # 步骤 2：明细是合计校验的输入（PRD 5.3 分类型合计口径）
    line_items = repo.document_line_items.find("document_id = %s", (document_id,), order="id")
    # 步骤 3：匹配审批流程，取首个节点与审批人（PRD 7.2 由后端按类型/金额/部门匹配）
    first_node, approver_id = approval_service.match_workflow(document)
    # 步骤 4：快照、实例与首个任务必须在同一事务内完成，任一失败整体回滚（PRD 11.1 事务边界）
    with transaction():
        snapshot, instance, task = runtime.flow().document_creation.submit(
            document, line_items, first_node, approver_id)
        repo.financial_documents.update(document.id, document_no=document.document_no,
                                        document_status=document.document_status,
                                        current_version=document.current_version)
        snapshot.id = repo.document_versions.insert(snapshot)
        instance.id = repo.approval_instances.insert(instance)
        task.instance_id = instance.id
        task.id = repo.approval_tasks.insert(task)
        runtime.flush_status_logs()
        runtime.flush_audit_logs()
    return {"document": document, "snapshot": snapshot, "instance": instance, "task": task}


def withdraw(document_id: int, role_codes: list[str], user_id: int) -> FinancialDocument:
    """撤回未处理的单据：pending_review → withdrawn（PRD 13.2 POST withdraw、7.3）。"""
    # 步骤 1：取单据并校验撤回权限（PRD 7.3 仅申请人可撤回）
    document = require_document(document_id)
    if not auth_service.can_edit_document(role_codes, user_id, document):
        raise PermissionDenied("仅申请人本人可撤回该单据")
    # 步骤 2：交环节一按 PRD 7.3 流转表流转，非法流转由流转表拦截
    document = runtime.flow().document_creation.withdraw(document)
    # 步骤 3：落库并同步状态与留痕
    repo.financial_documents.update(document.id, document_status=document.document_status)
    runtime.flush_status_logs()
    runtime.flush_audit_logs()
    return document


def void(document_id: int, role_codes: list[str], user_id: int) -> FinancialDocument:
    """作废符合条件的单据：draft / returned → voided（PRD 13.2 POST void、7.3）。"""
    # 步骤 1：取单据并校验作废权限
    document = require_document(document_id)
    if not auth_service.can_edit_document(role_codes, user_id, document):
        raise PermissionDenied("仅申请人本人可作废该单据")
    # 步骤 2：交环节一按 PRD 7.3 流转表流转
    document = runtime.flow().document_creation.void(document)
    # 步骤 3：落库并同步状态与留痕
    repo.financial_documents.update(document.id, document_status=document.document_status)
    runtime.flush_status_logs()
    runtime.flush_audit_logs()
    return document


def detail(document_id: int, role_codes: list[str], user_id: int) -> dict:
    """查询单据详情：基本信息、明细、附件、版本与审批进度（PRD 13.2 GET /documents/{id}）。"""
    # 步骤 1：取单据并校验数据权限（PRD 3.3）
    document = require_document(document_id)
    if not auth_service.can_view_document(role_codes, user_id, document):
        raise PermissionDenied("无权访问该单据")
    # 步骤 2：聚合明细、附件与版本（PRD 13.2 详情包含明细、附件、版本、审批进度）
    line_items = repo.document_line_items.find("document_id = %s", (document_id,), order="id")
    attachments = repo.document_attachments.find("document_id = %s", (document_id,), order="id")
    versions = repo.document_versions.find("document_id = %s", (document_id,), order="version_no")
    # 步骤 3：聚合审批实例与任务，形成审批进度
    instances = repo.approval_instances.find("document_id = %s", (document_id,), order="id")
    tasks = []
    for instance in instances:
        tasks += repo.approval_tasks.find("instance_id = %s", (instance.id,), order="id")
    # 步骤 4：聚合状态变化留痕
    status_logs = repo.document_status_logs.find("document_id = %s", (document_id,), order="id")
    return {"document": document, "line_items": line_items, "attachments": attachments,
            "versions": versions, "instances": instances, "tasks": tasks,
            "status_logs": status_logs}
