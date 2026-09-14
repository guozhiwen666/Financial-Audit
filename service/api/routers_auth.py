"""认证接口（PRD 13.1 认证）。

覆盖：用户登录并返回访问令牌、查询当前登录用户。
另含登出：PRD 2.7.14 要求访问令牌必须支持撤销，PRD 2.7.8 要求认证模块处理「登录、退出」，
故登出接口是这两条要求的落地入口。
"""

from typing import Annotated

from fastapi import APIRouter, Body, Header

from service.infrastructure import security
from service.business_services import auth_service
from service.api.deps import CurrentPrincipal
from service.api.serializers import as_dict
from service.infrastructure.errors import BadRequest

__all__ = ["router"]

router = APIRouter(tags=["认证"])


@router.post("/auth/login")
def login(payload: Annotated[dict, Body()]) -> dict:
    """用户登录并返回访问令牌（PRD 13.1 POST /auth/login）。"""
    # 步骤 1：用户名与密码均为必填
    username, password = payload.get("username"), payload.get("password")
    if not username or not password:
        raise BadRequest("缺少必填字段 username 或 password")
    # 步骤 2：交服务层校验密码哈希与账号状态，并签发带有效期的令牌（PRD 2.7.14）
    user, token, seconds = auth_service.login(username, password)
    # 步骤 3：返回令牌、有效期与用户信息；有效期按 PRD 13.10 要求显式告知
    return {"access_token": token, "token_type": "Bearer", "expires_in": seconds,
            "user": as_dict(user), "role_codes": auth_service.role_codes_of(user.id)}


@router.get("/auth/me")
def me(principal: CurrentPrincipal) -> dict:
    """查询当前登录用户（PRD 13.1 GET /auth/me）。"""
    # 步骤 1：按令牌载荷中的用户主键取用户；令牌有效即登录态有效
    user = auth_service.load_user(principal.user_id)
    return {"user": as_dict(user), "username": principal.username,
            "role_codes": principal.role_codes}


@router.post("/auth/logout")
def logout(principal: CurrentPrincipal,
           authorization: Annotated[str, Header()] = "") -> dict:
    """登出：撤销当前访问令牌（PRD 2.7.14 撤销机制、2.7.8 认证模块「退出」）。"""
    # 步骤 1：把令牌加入撤销名单——撤销后即使仍在有效期内也不再通过鉴权
    token = authorization.split(" ", 1)[-1].strip() if authorization else principal.token
    security.revoke_token(token)
    return {"revoked": True, "username": principal.username}
