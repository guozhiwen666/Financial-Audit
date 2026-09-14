"""认证与权限模块（PRD 3.1~3.3、11 章「认证与权限模块」、2.7.14）。

职责：登录、当前用户识别、角色权限判定、单据数据权限校验。
边界（PRD 11.1 权限前置）：权限校验在服务层统一拦截，禁止在查询语句之后做内存过滤；
故本模块提供 ``can_view_document`` 供服务层在取数前判定，而不是取回数据后再筛。
"""

from service.infrastructure import repository as repo
from service.infrastructure.errors import PermissionDenied  # 权限异常由 errors 统一承载（PRD 13.10）
from service.infrastructure.security import create_token, verify_password

__all__ = ["APPLICANT", "APPROVER", "FINANCE", "ADMIN", "ACTIVE_STATUS", "PermissionDenied",
           "login", "load_user", "role_codes_of", "can_view_all", "can_analyze", "can_review",
           "can_manage_rules", "can_manage_system", "can_edit_document", "can_view_document",
           "require"]

# 角色码常量：取值严格取自 PRD 3.1 的「角色码」列
APPLICANT = "applicant"  # 单据申请人
APPROVER = "approver"    # 审批人员
FINANCE = "finance"      # 财务人员
ADMIN = "admin"          # 系统管理员

# 账号启用状态：PRD 未列举 users.status / roles.status 的取值集合，故约定 active 为启用，
# 其余取值一律视为停用（登录与角色判定均据此拦截）。
ACTIVE_STATUS = "active"

# 权限矩阵（PRD 3.2）——逐项对应矩阵中的能力行
VIEW_ALL_ROLES = {APPROVER, FINANCE, ADMIN}    # 查看全部单据
ANALYZE_ROLES = {APPROVER, FINANCE, ADMIN}     # 发起风险分析、查看风险面板与证据
REVIEW_ROLES = {APPROVER}                      # 填写复核意见、提交审批结果
RULE_ROLES = {FINANCE, ADMIN}                  # 维护审核规则、市场价、供应商信息
SYSTEM_ROLES = {ADMIN}                         # 维护用户 / 角色 / 权限 / 审批流程 / 系统参数
EDIT_ROLES = {APPLICANT}                       # 创建与编辑本人草稿、维护明细与附件


def load_user(user_id: int):
    """按主键取用户，不存在时返回 None。"""
    return repo.users.get(user_id)


def role_codes_of(user_id: int) -> list[str]:
    """查询用户拥有的角色码列表（经 user_roles 关联表）。"""
    # 步骤 1：查关联得到角色主键
    links = repo.user_roles.find("user_id = %s", (user_id,))
    codes: list[str] = []
    for link in links:
        # 步骤 2：停用角色不生效（PRD 3.3 要求校验登录状态与权限）
        role = repo.roles.get(link.role_id) if link.role_id else None
        if role is not None and role.status == ACTIVE_STATUS:
            codes.append(role.role_code)
    return codes


def login(username: str, password: str) -> tuple[object, str, int]:
    """用户登录：校验用户名与密码，返回 (用户实体, 访问令牌, 有效期秒数)。"""
    # 步骤 1：按用户名查用户——用户名唯一，取首条
    rows = repo.users.find("username = %s", (username,))
    if not rows:
        raise PermissionDenied("用户名或密码错误")
    user = rows[0]
    # 步骤 2：校验密码哈希（PRD 2.7.14 密码必须使用安全哈希保存）
    if not verify_password(password, user.password_hash):
        raise PermissionDenied("用户名或密码错误")
    # 步骤 3：校验账号状态，非启用状态一律拒绝登录
    if user.status != ACTIVE_STATUS:
        raise PermissionDenied("账号已停用")
    # 步骤 4：签发带有效期的访问令牌（PRD 2.7.14 令牌须设置有效期）
    token, seconds = create_token(user.id or 0, user.username or "", role_codes_of(user.id or 0))
    return user, token, seconds


def can_view_all(role_codes: list[str]) -> bool:
    """是否可见全部单据（PRD 3.2：审批人员、财务人员、系统管理员）。"""
    return bool(VIEW_ALL_ROLES & set(role_codes))


def can_analyze(role_codes: list[str]) -> bool:
    """是否可发起风险分析并查看风险面板与证据（PRD 3.2）。"""
    return bool(ANALYZE_ROLES & set(role_codes))


def can_review(role_codes: list[str]) -> bool:
    """是否可填写复核意见、提交审批结果（PRD 3.2）。"""
    return bool(REVIEW_ROLES & set(role_codes))


def can_manage_rules(role_codes: list[str]) -> bool:
    """是否可维护审核规则、市场价与供应商信息（PRD 3.2）。"""
    return bool(RULE_ROLES & set(role_codes))


def can_manage_system(role_codes: list[str]) -> bool:
    """是否可维护用户、角色、权限、审批流程与系统参数（PRD 3.2）。"""
    return bool(SYSTEM_ROLES & set(role_codes))


def can_edit_document(role_codes: list[str], user_id: int, document) -> bool:
    """是否可编辑指定单据：申请人仅限本人单据（PRD 3.2、3.3 数据权限）。"""
    return bool(EDIT_ROLES & set(role_codes)) and document.applicant_id == user_id


def can_view_document(role_codes: list[str], user_id: int, document) -> bool:
    """是否可查看指定单据（PRD 3.3 数据权限规则）。"""
    # 步骤 1：审批人员 / 财务人员 / 系统管理员可见全部单据
    if can_view_all(role_codes):
        return True
    # 步骤 2：申请人默认仅可见本人单据
    return document.applicant_id == user_id


def require(condition: bool, message: str) -> None:
    """断言权限条件，不满足时抛出 PermissionDenied。"""
    if not condition:
        raise PermissionDenied(message)
