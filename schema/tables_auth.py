"""身份与权限表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空以表示"未赋值"，
不臆造约束。
"""

from dataclasses import dataclass        # dataclass：声明纯字段结构
from datetime import datetime            # datetime：创建/更新时间戳

__all__ = [
    "User",              # 用户表
    "Role",              # 角色表
    "Permission",        # 权限表
    "UserRole",          # 用户-角色关联表
    "RolePermission",    # 角色-权限关联表
]


@dataclass
class User:
    """users 表：系统登录用户。"""

    id: int                                        # 主键
    username: str | None = None                    # 登录用户名，系统内唯一
    display_name: str | None = None                # 展示名称，界面与审批记录中显示
    password_hash: str | None = None               # 密码的安全哈希值，禁止保存明文
    status: str | None = None                      # 账号状态（PRD 未列举取值，保持字符串）
    created_at: datetime | None = None             # 创建时间
    updated_at: datetime | None = None             # 最近一次更新时间


@dataclass
class Role:
    """roles 表：角色定义（申请人/审批人员/财务人员/系统管理员等）。"""

    id: int                                        # 主键
    role_code: str | None = None                   # 角色编码，程序内引用用的稳定标识
    role_name: str | None = None                   # 角色名称，展示用
    status: str | None = None                      # 角色状态（PRD 未列举取值，保持字符串）
    created_at: datetime | None = None             # 创建时间
    updated_at: datetime | None = None             # 最近一次更新时间


@dataclass
class Permission:
    """permissions 表：权限点定义。"""

    id: int                                        # 主键
    permission_code: str | None = None             # 权限编码，校验时比对的标识
    permission_name: str | None = None             # 权限名称，展示用
    resource_type: str | None = None               # 权限作用的资源类型（单据/附件/规则等）
    action_type: str | None = None                 # 允许的动作类型（查看/创建/审批等）


@dataclass
class UserRole:
    """user_roles 表：用户与角色的多对多关联。"""

    id: int                                        # 主键
    user_id: int | None = None                     # 用户主键，指向 users.id
    role_id: int | None = None                     # 角色主键，指向 roles.id


@dataclass
class RolePermission:
    """role_permissions 表：角色与权限点的多对多关联。"""

    id: int                                        # 主键
    role_id: int | None = None                     # 角色主键，指向 roles.id
    permission_id: int | None = None               # 权限主键，指向 permissions.id
