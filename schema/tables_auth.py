"""身份与权限表结构（PRD 2.7.10）。

_nullability_：PRD 未定义各列可空性，此处仅主键必填，其余字段一律可空以表示"未赋值"，
不臆造约束。
"""

from dataclasses import dataclass
from datetime import datetime

__all__ = ["User", "Role", "Permission", "UserRole", "RolePermission"]


@dataclass
class User:
    """users 表。"""

    id: int
    username: str | None = None
    display_name: str | None = None
    password_hash: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Role:
    """roles 表。"""

    id: int
    role_code: str | None = None
    role_name: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Permission:
    """permissions 表。"""

    id: int
    permission_code: str | None = None
    permission_name: str | None = None
    resource_type: str | None = None
    action_type: str | None = None


@dataclass
class UserRole:
    """user_roles 表。"""

    id: int
    user_id: int | None = None
    role_id: int | None = None


@dataclass
class RolePermission:
    """role_permissions 表。"""

    id: int
    role_id: int | None = None
    permission_id: int | None = None
