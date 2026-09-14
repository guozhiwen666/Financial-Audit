"""审批流程模块（PRD 11 章「审批流程模块」、13.7、7.2、7.3）。

职责：流程定义维护、适用条件匹配、审批实例创建（由单据提交触发）、节点流转与审批任务管理。
边界：审批结论只能由有权限的人员提交（PRD 2.7.14）；本模块只做匹配、取数与落库，
状态流转一律交环节三按 PRD 7.3 流转表执行。
"""

from decimal import Decimal  # 金额区间的精确比较

from schema.enums import ApprovalTaskStatus  # 审批任务状态（任务可取的前置判定）
from service.infrastructure import repository as repo, runtime
from service.business_services import auth_service
from service.infrastructure.database import transaction
from service.infrastructure.errors import BadRequest, Conflict, NotFound, PermissionDenied

__all__ = ["match_workflow", "list_tasks", "approve", "return_back", "reject",
           "list_workflows", "create_workflow", "update_workflow", "WORKFLOW_FIELDS"]

# 流程与节点可由接口写入的列（取数据表真实列，不含主键与时间戳）
WORKFLOW_FIELDS = tuple(c for c in repo.approval_workflows.columns
                        if c not in ("id", "created_at", "updated_at"))
NODE_FIELDS = tuple(c for c in repo.approval_workflow_nodes.columns
                    if c not in ("id", "created_at"))
# 流程启用状态：PRD 未列举 status 取值，约定 active 为启用
ACTIVE = "active"


def _pick_approver(approver_role: str | None) -> int:
    """按审批角色取一名可用审批人（PRD 7.2 生成审批任务）。"""
    # 步骤 1：在启用用户中挑出拥有该角色的第一个用户
    if not approver_role:
        raise Conflict("审批节点未配置审批角色，无法生成审批任务")
    for user in repo.users.find("status = %s", (auth_service.ACTIVE_STATUS,), order="id"):
        if approver_role in auth_service.role_codes_of(user.id):
            return user.id
    raise Conflict("未找到审批角色 %s 下的可用审批人（PRD 7.2）" % approver_role)


def _matches(workflow, document) -> bool:
    """判定流程的适用条件是否命中当前单据（PRD 2.7.4 按单据类型、金额区间和部门维护流程）。

    条件结构：PRD 未规定 ``match_conditions_json`` 的字段，故约定
    ``{"min_amount": 起（含）, "max_amount": 止（不含）, "department": 部门}``，缺省即不限制。
    """
    conditions = workflow.match_conditions_json or {}
    amount = document.total_amount
    # 步骤 1：金额区间——未配置的边界视为不限
    if conditions.get("min_amount") is not None:
        if amount is None or amount < Decimal(str(conditions["min_amount"])):
            return False
    if conditions.get("max_amount") is not None:
        if amount is None or amount >= Decimal(str(conditions["max_amount"])):
            return False
    # 步骤 2：部门——申请部门或预算部门任一命中即可
    department = conditions.get("department")
    if department and department not in (document.applicant_department, document.budget_department):
        return False
    return True


def match_workflow(document) -> tuple[object, int]:
    """匹配适用审批流程并取首个节点与审批人（PRD 7.2 提交时生成实例与首个任务）。"""
    # 步骤 1：按单据类型筛出启用中的流程，逐一比对适用条件
    for workflow in repo.approval_workflows.find(
            "document_type = %s AND status = %s",
            (document.document_type.value, ACTIVE), order="id"):
        if not _matches(workflow, document):
            continue
        # 步骤 2：取节点顺序最小的节点作为首个审批节点
        nodes = repo.approval_workflow_nodes.find(
            "workflow_id = %s", (workflow.id,), order="node_order", limit=1)
        if not nodes:
            continue
        return nodes[0], _pick_approver(nodes[0].approver_role)
    raise Conflict("未匹配到适用的审批流程，请先配置流程（PRD 7.2）")


def _next_node(instance) -> tuple[object | None, int | None]:
    """取当前节点之后的下一节点与审批人；已是末节点时返回 (None, None)（PRD 7.2）。"""
    # 步骤 1：以实例当前节点为基准，取其所在的流程
    current = repo.approval_workflow_nodes.get(instance.current_node_id) \
        if instance.current_node_id else None
    if current is None:
        return None, None
    # 步骤 2：按节点顺序取紧随其后的节点
    following = repo.approval_workflow_nodes.find(
        "workflow_id = %s AND node_order > %s", (current.workflow_id, current.node_order),
        order="node_order", limit=1)
    if not following:
        return None, None
    return following[0], _pick_approver(following[0].approver_role)


def list_tasks(role_codes: list[str], user_id: int, status: str | None = None) -> list:
    """查询当前用户的审批任务（PRD 13.7 GET /approval-tasks）。"""
    # 步骤 1：仅审批人员有审批任务（PRD 3.2 提交审批结果）
    if not auth_service.can_review(role_codes):
        raise PermissionDenied("当前用户不是审批人员")
    # 步骤 2：按审批人与状态筛选
    if status:
        return repo.approval_tasks.find("approver_id = %s AND task_status = %s",
                                        (user_id, status), order="id DESC")
    return repo.approval_tasks.find("approver_id = %s", (user_id,), order="id DESC")


def _load_task(task_id: int, role_codes: list[str], user_id: int) -> tuple[object, object, object]:
    """取审批任务并校验处理权限，返回 (任务, 实例, 单据)。"""
    # 步骤 1：仅审批人员可处理审批任务（PRD 3.2）
    if not auth_service.can_review(role_codes):
        raise PermissionDenied("当前用户不是审批人员，无权处理审批任务")
    task = repo.approval_tasks.get(task_id)
    if task is None:
        raise NotFound("审批任务不存在：%s" % task_id)
    # 步骤 2：仅该任务的审批人本人可处理（PRD 3.2 数据权限）
    if task.approver_id != user_id:
        raise PermissionDenied("仅该任务的审批人可处理")
    # 步骤 3：仅待处理任务可操作，避免重复审批（PRD 11.1 幂等性）
    if task.task_status != ApprovalTaskStatus.PENDING:
        raise Conflict("任务已处理，当前状态 %s" % task.task_status.value)
    # 步骤 4：取实例与单据——状态流转的作用对象
    instance = repo.approval_instances.get(task.instance_id)
    if instance is None:
        raise NotFound("审批实例不存在：%s" % task.instance_id)
    document = repo.financial_documents.get(instance.document_id)
    if document is None:
        raise NotFound("单据不存在：%s" % instance.document_id)
    return task, instance, document


def _settle(task, instance, document, comment: str | None, action: str) -> dict:
    """统一落库审批结论：任务、实例、单据状态与状态留痕（PRD 7.2、7.3）。"""
    task.review_comment = comment
    # 步骤 1：交环节三执行流转；结论处理与状态机均在环节内完成（PRD 7.3）
    with transaction():
        if action == "approve":
            processed, next_task = runtime.flow().approval.approve(
                document, instance, task, *_next_node(instance))
        else:
            method = (runtime.flow().approval.return_back if action == "return"
                      else runtime.flow().approval.reject)
            processed, next_task = method(document, instance, task), None
        # 步骤 2：回写任务
        repo.approval_tasks.update(task.id, task_status=task.task_status,
                                   review_comment=task.review_comment,
                                   processed_at=task.processed_at)
        # 步骤 3：非末节点通过时生成下一节点任务
        if next_task is not None:
            next_task.instance_id = instance.id
            next_task.id = repo.approval_tasks.insert(next_task)
        # 步骤 4：回写实例与单据状态
        repo.approval_instances.update(instance.id, instance_status=instance.instance_status,
                                       current_node_id=instance.current_node_id,
                                       finished_at=instance.finished_at)
        repo.financial_documents.update(document.id, document_status=document.document_status)
        # 步骤 5：状态留痕与审计留痕落库（PRD 2.7.14）
        runtime.flush_status_logs()
        runtime.flush_audit_logs()
    return {"task": processed, "next_task": next_task, "instance": instance, "document": document}


def approve(task_id: int, role_codes: list[str], user_id: int, comment: str | None = None) -> dict:
    """通过审批任务：末节点通过则单据状态变为 approved（PRD 13.7 POST approve）。"""
    return _settle(*_load_task(task_id, role_codes, user_id), comment, "approve")


def return_back(task_id: int, role_codes: list[str], user_id: int,
                comment: str | None = None) -> dict:
    """退回审批任务：允许申请人修改后重新提交（PRD 13.7 POST return）。"""
    return _settle(*_load_task(task_id, role_codes, user_id), comment, "return")


def reject(task_id: int, role_codes: list[str], user_id: int, comment: str | None = None) -> dict:
    """驳回审批任务：单据进入 rejected 终态（PRD 13.7 POST reject）。"""
    return _settle(*_load_task(task_id, role_codes, user_id), comment, "reject")


def list_workflows() -> list:
    """查询审批流程定义（PRD 13.7 GET /approval-workflows）。"""
    return repo.approval_workflows.find(order="id")


def create_workflow(payload: dict, role_codes: list[str]) -> dict:
    """创建审批流程及其节点（PRD 13.7 POST /approval-workflows）。"""
    # 步骤 1：仅系统管理员可维护审批流程（PRD 3.2）
    if not auth_service.can_manage_system(role_codes):
        raise PermissionDenied("仅系统管理员可维护审批流程")
    # 步骤 2：字段白名单校验（不含节点，节点单独传入）
    unknown = set(payload) - set(WORKFLOW_FIELDS) - {"nodes"}
    if unknown:
        raise BadRequest("不支持的字段：%s" % "、".join(sorted(unknown)))
    # 步骤 3：流程与节点须一并落库，避免出现无节点的空流程
    with transaction():
        workflow = repo.approval_workflows.model(
            id=0, **{name: repo.approval_workflows.coerce(name, value)
                     for name, value in payload.items() if name in WORKFLOW_FIELDS})
        workflow.id = repo.approval_workflows.insert(workflow)
        for node in payload.get("nodes") or []:
            unknown_node = set(node) - set(NODE_FIELDS)
            if unknown_node:
                raise BadRequest("节点不支持的字段：%s" % "、".join(sorted(unknown_node)))
            entity = repo.approval_workflow_nodes.model(
                id=0, workflow_id=workflow.id,
                **{name: repo.approval_workflow_nodes.coerce(name, value)
                   for name, value in node.items()})
            entity.id = repo.approval_workflow_nodes.insert(entity)
    return {"workflow": workflow}


def update_workflow(workflow_id: int, payload: dict, role_codes: list[str]) -> object:
    """更新审批流程（PRD 13.7 PATCH /approval-workflows/{workflow_id}）。"""
    # 步骤 1：仅系统管理员可维护审批流程（PRD 3.2）
    if not auth_service.can_manage_system(role_codes):
        raise PermissionDenied("仅系统管理员可维护审批流程")
    # 步骤 2：流程必须存在
    workflow = repo.approval_workflows.get(workflow_id)
    if workflow is None:
        raise NotFound("审批流程不存在：%s" % workflow_id)
    # 步骤 3：白名单校验后更新
    unknown = set(payload) - set(WORKFLOW_FIELDS)
    if unknown:
        raise BadRequest("不支持的字段：%s" % "、".join(sorted(unknown)))
    values = {name: repo.approval_workflows.coerce(name, value) for name, value in payload.items()}
    if values:
        repo.approval_workflows.update(workflow_id, **values)
    return repo.approval_workflows.get(workflow_id)
