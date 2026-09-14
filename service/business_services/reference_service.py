"""规则与参考数据模块（PRD 11 章「规则引擎模块」「供应商模块」「日志模块」、13.8、13.9）。

职责：审核规则的维护（金额容差、费用标准、市场价区间、异常阈值）、供应商风险信息查询、
操作审计日志查询。
边界：规则是**阈值的唯一来源**（PRD 12.3 G07）；本模块只维护配置本身，不参与规则判定；
规则变更必须记录操作人、操作时间与变更内容（PRD 2.7.14）。
"""

from datetime import datetime, timezone  # 规则更新时间与留痕时间

from schema.tables_rules import ReviewRule  # 审核规则实体
from service.infrastructure import repository as repo, runtime
from service.business_services import auth_service
from service.infrastructure.errors import BadRequest, NotFound, PermissionDenied

__all__ = ["RULE_FIELDS", "list_rules", "create_rule", "update_rule", "supplier_risks",
           "list_audit_logs", "list_market_prices", "list_suppliers"]

# 可由接口写入的列：取数据表真实列（PRD 12.3 G07 review_rules 的字段）
RULE_FIELDS = tuple(c for c in repo.review_rules.columns
                    if c not in ("id", "updated_by", "updated_at"))


def list_rules(role_codes: list[str]) -> list[ReviewRule]:
    """查询审核规则（PRD 13.9 GET /rules）。"""
    # 步骤 1：规则含企业费用与阈值口径，仅财务人员与系统管理员可查看（PRD 3.2）
    if not auth_service.can_manage_rules(role_codes):
        raise PermissionDenied("仅财务人员与系统管理员可查看审核规则（PRD 3.2）")
    return repo.review_rules.find(order="id")


def create_rule(payload: dict, role_codes: list[str], user_id: int) -> ReviewRule:
    """创建审核规则（PRD 13.9 POST /rules）。"""
    # 步骤 1：权限校验（PRD 3.2 维护审核规则）
    if not auth_service.can_manage_rules(role_codes):
        raise PermissionDenied("仅财务人员与系统管理员可维护审核规则（PRD 3.2）")
    # 步骤 2：规则编码与名称为定位规则的必要信息，必填
    for name in ("rule_code", "rule_name"):
        if not payload.get(name):
            raise BadRequest("缺少必填字段 %s（PRD 12.3 G07）" % name)
    # 步骤 3：字段白名单校验，避免自造字段
    unknown = set(payload) - set(RULE_FIELDS)
    if unknown:
        raise BadRequest("不支持的字段：%s" % "、".join(sorted(unknown)))
    # 步骤 4：构造并落库；操作人与时间一并记录（PRD 2.7.14 规则变更留痕）
    rule = ReviewRule(id=0, updated_by=user_id, updated_at=datetime.now(timezone.utc))
    for name, value in payload.items():
        setattr(rule, name, repo.review_rules.coerce(name, value))
    rule.id = repo.review_rules.insert(rule)
    # 步骤 5：写审计留痕——记录变更内容（PRD 2.7.14）
    runtime.flow().audit_log.record("create_rule", "review_rules", rule.id, user_id,
                                    {"rule_code": rule.rule_code, "params_json": rule.params_json})
    runtime.flush_audit_logs()
    return rule


def update_rule(rule_id: int, payload: dict, role_codes: list[str], user_id: int) -> ReviewRule:
    """更新审核规则（PRD 13.9 PATCH /rules/{rule_id}）。"""
    # 步骤 1：权限校验（PRD 3.2）
    if not auth_service.can_manage_rules(role_codes):
        raise PermissionDenied("仅财务人员与系统管理员可维护审核规则（PRD 3.2）")
    # 步骤 2：规则必须存在
    rule = repo.review_rules.get(rule_id)
    if rule is None:
        raise NotFound("审核规则不存在：%s" % rule_id)
    # 步骤 3：字段白名单校验
    unknown = set(payload) - set(RULE_FIELDS)
    if unknown:
        raise BadRequest("不支持的字段：%s" % "、".join(sorted(unknown)))
    # 步骤 4：更新并记录操作人与时间（PRD 2.7.14）
    values = {name: repo.review_rules.coerce(name, value) for name, value in payload.items()}
    values["updated_by"] = user_id
    values["updated_at"] = datetime.now(timezone.utc)
    repo.review_rules.update(rule_id, **values)
    # 步骤 5：写审计留痕——留痕须含变更内容，故记录变更前后的阈值（PRD 2.7.14）
    runtime.flow().audit_log.record("update_rule", "review_rules", rule_id, user_id,
                                    {"before": rule.params_json,
                                     "after": values.get("params_json")})
    runtime.flush_audit_logs()
    return repo.review_rules.get(rule_id)


def supplier_risks(supplier_code: str, role_codes: list[str], user_id: int) -> dict:
    """查询供应商风险信息（PRD 13.8 GET /suppliers/{supplier_code}/risks）。"""
    # 步骤 1：供应商档案属财务数据，仅财务人员与系统管理员可查看（PRD 3.2）
    if not auth_service.can_manage_rules(role_codes) and not auth_service.can_view_all(role_codes):
        raise PermissionDenied("无权查看供应商风险信息")
    # 步骤 2：按供应商编码定位档案
    rows = repo.supplier_profiles.find("supplier_code = %s", (supplier_code,), limit=1)
    if not rows:
        raise NotFound("供应商不存在：%s" % supplier_code)
    supplier = rows[0]
    # 步骤 3：汇总该供应商相关的历史单据（PRD 13.8 历史付款与异常记录）
    name = supplier.supplier_name or ""
    history = repo.financial_documents.find("(supplier_name = %s OR payee_name = %s)",
                                            (name, name), order="id DESC")
    # 步骤 4：汇总该供应商相关单据上的风险项，供面板展示（PRD 13.8 风险标签与异常记录）
    findings = []
    for document in history:
        tasks = repo.analysis_tasks.find("document_id = %s", (document.id,), order="id DESC")
        for task in tasks:
            findings += repo.risk_findings.find("task_id = %s", (task.id,))
    return {"supplier": supplier, "history": history, "findings": findings}


def list_suppliers(role_codes: list[str]) -> list:
    """查询供应商档案列表（PRD 2.7.4 供应商风险页所需的档案数据）。"""
    if not auth_service.can_manage_rules(role_codes) and not auth_service.can_view_all(role_codes):
        raise PermissionDenied("无权查看供应商档案")
    return repo.supplier_profiles.find(order="id")


def list_market_prices(role_codes: list[str]) -> list:
    """查询市场价参考数据（PRD 3.2 财务人员维护市场价参考数据）。"""
    if not auth_service.can_manage_rules(role_codes):
        raise PermissionDenied("仅财务人员与系统管理员可查看市场价参考数据（PRD 3.2）")
    return repo.market_price_references.find(order="id")


def list_audit_logs(role_codes: list[str], user_id: int, resource_type: str | None = None,
                    limit: int = 200) -> list:
    """查询操作日志（PRD 2.7.4 审核记录页、13 章日志查询）。"""
    # 步骤 1：审计日志属管理面数据，仅财务人员与系统管理员可查看（PRD 3.2）
    if not auth_service.can_manage_rules(role_codes):
        raise PermissionDenied("无权查看操作日志（PRD 3.2）")
    # 步骤 2：可按资源类型过滤；按时间倒序返回最近记录
    if resource_type:
        return repo.audit_logs.find("resource_type = %s", (resource_type,),
                                    order="id DESC", limit=limit)
    return repo.audit_logs.find(order="id DESC", limit=limit)
