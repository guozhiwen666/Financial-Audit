"""接口依赖：登录态解析与当前主体注入（PRD 13 章统一鉴权、3.3 权限校验）。

所有接口一律先经本模块解析 Bearer 访问令牌，拿到当前登录主体后才能进业务；
服务层的权限校验以该主体的角色码为唯一依据（PRD 11.1 权限前置）。
"""

from typing import Annotated  # 依赖注入的类型标注

from fastapi import Depends, Header  # 从请求头取令牌

from service.infrastructure import security
from service.infrastructure.errors import PermissionDenied  # 未登录一律拒绝（PRD 3.3）

__all__ = ["Principal", "principal", "CurrentPrincipal"]

_BEARER_PREFIX = "bearer "  # 统一鉴权方案（PRD 13 章）


class Principal:
    """当前登录主体：用户主键、用户名与角色码。"""

    def __init__(self, payload: dict, token: str) -> None:
        # 令牌载荷解析出的身份信息；角色码来自签发时刻的判定结果
        self.token = token
        self.user_id = int(payload["sub"])
        self.username = payload.get("username") or ""
        self.role_codes = list(payload.get("roles") or [])


def principal(authorization: Annotated[str, Header()] = "") -> Principal:
    """从 ``Authorization: Bearer <token>`` 解析当前登录主体。"""
    # 步骤 1：请求头缺失或方案不符一律拒绝
    if not authorization.lower().startswith(_BEARER_PREFIX):
        raise PermissionDenied("缺少访问令牌（PRD 13 章统一鉴权）")
    # 步骤 2：解析并校验令牌签名与有效期；已撤销的令牌同样无效（PRD 2.7.14）
    token = authorization[len(_BEARER_PREFIX):].strip()
    payload = security.decode_token(token)
    if payload is None:
        raise PermissionDenied("访问令牌无效、已过期或已撤销")
    return Principal(payload, token)


# 接口签名的统一写法：principal: CurrentPrincipal
CurrentPrincipal = Annotated[Principal, Depends(principal)]
