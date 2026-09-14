"""智能分析模块（PRD 11 章「智能分析模块」、13.6、9.1、20.7）。

职责：聚合结构化数据、附件内容、规则结果、市场价与供应商信息，驱动主流程产出风险结论，
并把解析结果、分析任务、风险项与报告落库。
边界：金额计算、阈值判定与等级取值全部由规则引擎与环节确定性实现（PRD 20.1 P1），
本模块只负责「取数 → 装配上下文 → 驱动主流程 → 落库」，不做任何风险判断。
"""

from schema.enums import AnalysisTaskStatus  # 分析任务状态（进度展示用）
from service.infrastructure import repository as repo, runtime
from service.business_services import attachment_service, auth_service, document_service
from service.infrastructure.converters import to_decimal  # 合同金额文本的转换
from service.infrastructure.database import transaction
from service.infrastructure.errors import NotFound, PermissionDenied

__all__ = ["create_analysis", "get_task", "get_findings", "require_task", "build_context",
           "persist", "CONTRACT_AMOUNT_KEYS"]

# 合同金额的抽取键名候选：PRD 未固定字段提取结果的键名，故按候选清单容错（与 engine 同口径）
CONTRACT_AMOUNT_KEYS = ("contract_amount", "contract_total_amount", "合同金额", "合同总额")
# 规则启用状态：PRD 未列举 status 取值，约定 active 为启用
ACTIVE = "active"


def _in_attachments(repo_obj, attachment_ids: list[int]) -> list:
    """按附件主键集合查询其名下的记录（仅本单据的发票）。"""
    if not attachment_ids:
        return []
    placeholders = ", ".join(["%s"] * len(attachment_ids))
    return repo_obj.find("attachment_id IN (%s)" % placeholders, attachment_ids, order="id")


def _not_in_attachments(repo_obj, attachment_ids: list[int]) -> list:
    """查询不属于本单据的记录，作为历史数据（R07 历史金额突增、R10 重复票据）。"""
    if not attachment_ids:
        return repo_obj.find(order="id")
    placeholders = ", ".join(["%s"] * len(attachment_ids))
    return repo_obj.find("attachment_id NOT IN (%s)" % placeholders, attachment_ids, order="id")


def _contract_amount(parse_results: list) -> object:
    """从合同类附件的解析字段中取合同金额（PRD 12.1 单据表无该列，故取自附件解析结果）。"""
    for result in parse_results:
        fields = result.fields_json or {}
        for key in CONTRACT_AMOUNT_KEYS:
            if fields.get(key):
                return to_decimal(fields[key])
    return None


def _find_supplier(document):
    """按供应商名称或收款单位匹配供应商档案（PRD 11 章「供应商模块」）。"""
    # 步骤 1：优先用合同供应商名称，其次用收款单位
    name = document.supplier_name or document.payee_name
    if not name:
        return None
    rows = repo.supplier_profiles.find("supplier_name = %s", (name,), limit=1)
    return rows[0] if rows else None


def build_context(document, line_items: list, attachments: list) -> dict:
    """装配分析上下文：单据、明细、附件与规则引擎所需的参考数据（PRD 9.1、20.7）。

    参考数据一律取自数据库；表内无数据来源的项（节假日日历、常驻地区、职级）不传入，
    对应规则子模式据 PRD 20.7 自行跳过，不臆造数据。
    """
    attachment_ids = [a.id for a in attachments if a.id]
    # 步骤 1：规则配置是阈值的唯一来源；未配置即该规则不产出（PRD 20.7）
    rules = repo.review_rules.find("status = %s", (ACTIVE,), order="id")
    # 步骤 2：本单据的发票与历史发票/历史明细，供 R01、R07、R10 使用
    invoices = _in_attachments(repo.invoice_records, attachment_ids)
    return {
        "document": document,
        "line_items": line_items,
        # 附件路径转绝对路径后才能被解析环节打开（库中仍保存受控的相对路径，PRD 16）
        "attachments": attachment_service.for_parsing(attachments),
        "rules": rules,
        "invoices": invoices,
        "expense_standards": repo.expense_standards.find(order="id"),
        "market_prices": repo.market_price_references.find(order="id"),
        "supplier": _find_supplier(document),
        "invoice_history": _not_in_attachments(repo.invoice_records, attachment_ids),
        "expense_history": repo.document_line_items.find(
            "document_id != %s", (document.id,), order="id"),
        # 合同金额得在解析之后才能确定，此处先占位，由 persist 前按解析结果回填
        "contract_amount": None,
    }


def persist(state: dict) -> dict:
    """把分析产出落库：解析结果、分析任务、风险项、报告与审计留痕（PRD 7.2 保存分析结果）。"""
    # 步骤 1：附件解析状态回写（PRD 5.4 解析状态管理）
    for attachment in state.get("attachments") or []:
        if attachment.id:
            repo.document_attachments.update(attachment.id, parse_status=attachment.parse_status)
    # 步骤 2：解析结果归档（A2 产出的主键为 0，插入后回填）
    for result in state.get("parse_results") or []:
        if not result.id:
            result.id = repo.attachment_parse_results.insert(result)
    # 步骤 3：分析任务落库
    task = state.get("analysis_task")
    if task is not None and not task.id:
        task.id = repo.analysis_tasks.insert(task)
    # 步骤 4：风险项逐条落库并挂到任务下（A3 产出的主键为 0）
    for finding in state.get("findings") or []:
        if finding.id:
            continue
        finding.task_id = task.id if task is not None else finding.task_id
        finding.id = repo.risk_findings.insert(finding)
    # 步骤 5：报告落库——报告在图中以任务主键 0 占位生成，故此处对齐为真实任务主键
    report = state.get("report")
    if report is not None:
        if not report.task_id and task is not None:
            report.task_id = task.id
        if not report.id:
            report.id = repo.review_reports.insert(report)
    # 步骤 6：审计留痕落库（PRD 2.7.14）
    runtime.flush_audit_logs()
    return state


def create_analysis(document_id: int, role_codes: list[str], user_id: int) -> dict:
    """创建并执行单据风险分析任务（PRD 13.6 POST /documents/{document_id}/analysis）。"""
    # 步骤 1：取单据并校验「发起风险分析」权限（PRD 3.2）
    document = document_service.require_document(document_id)
    if not auth_service.can_analyze(role_codes):
        raise PermissionDenied("当前用户无权发起风险分析（PRD 3.2）")
    # 步骤 2：取明细与附件，装配分析上下文
    line_items = repo.document_line_items.find("document_id = %s", (document_id,), order="id")
    attachments = repo.document_attachments.find("document_id = %s", (document_id,), order="id")
    context = build_context(document, line_items, attachments)
    # 步骤 3：写入审计留痕——分析任务的发起属必留痕动作（PRD 2.7.14）
    runtime.flow().audit_log.record("create_analysis", "financial_documents", document_id,
                                    user_id, {"document_no": document.document_no})
    # 步骤 4：在同一事务内驱动分析图并落库，任一失败整体回滚（PRD 11.1 事务边界）
    with transaction():
        state = runtime.flow().run_analysis(context)
        persist(state)
    return state


def require_task(task_id: int, role_codes: list[str], user_id: int):
    """取分析任务并校验数据权限（PRD 3.3、13.6）。"""
    # 步骤 1：任务必须存在
    task = repo.analysis_tasks.get(task_id)
    if task is None:
        raise NotFound("分析任务不存在：%s" % task_id)
    # 步骤 2：按任务所属单据校验可见性——无权看单据即无权看任务
    document = document_service.require_document(task.document_id)
    if not auth_service.can_view_document(role_codes, user_id, document):
        raise PermissionDenied("无权访问该分析任务")
    return task


def get_task(task_id: int, role_codes: list[str], user_id: int):
    """查询分析任务状态与当前步骤（PRD 13.6 GET /analysis-tasks/{task_id}）。"""
    task = require_task(task_id, role_codes, user_id)
    # 步骤 1：附上进度百分比——状态越靠后进度越高，供前端展示（PRD 14.2 task_status）
    order = [s.value for s in AnalysisTaskStatus]
    progress = int(round((order.index(task.task_status.value) + 1) * 100 / len(order))) \
        if task.task_status.value in order else 0
    return {"task": task, "progress": progress}


def get_findings(task_id: int, role_codes: list[str], user_id: int) -> list:
    """查询风险项列表（PRD 13.6 GET /analysis-tasks/{task_id}/findings）。"""
    require_task(task_id, role_codes, user_id)
    # 步骤 1：按风险等级降序返回，高风险优先呈现（PRD 15 风险项列表）
    rows = repo.risk_findings.find("task_id = %s", (task_id,))
    rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(rows, key=lambda f: (rank.get(f.risk_level.value if f.risk_level else "", 9),
                                       f.id))
