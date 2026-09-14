"""认证安全：密码哈希与访问令牌（PRD 2.7.14）。

边界（PRD 2.7.14）：密码必须以安全哈希保存；访问令牌必须设置有效期与撤销机制。
实现说明：密码用 PBKDF2-HMAC-SHA256 加盐哈希（标准库 hashlib，不引入额外依赖）；
令牌用 PyJWT 签发，载荷含用户、角色与有效期；撤销名单由本模块在进程内维护
（PRD 12.1 的表清单中没有令牌表，故不新增数据结构承载撤销名单）。
"""

import base64  # 哈希摘要的十六进制安全编码
import hashlib  # PBKDF2 密码哈希（标准库，无需额外依赖）
import hmac  # 恒定时间比较，防时序攻击
import secrets  # 盐值与令牌标识的安全随机源
import time  # 令牌签发与过期时间

import jwt  # 已声明依赖（pyproject.toml）

from config.config import auth_config  # 令牌密钥与有效期配置

__all__ = ["hash_password", "verify_password", "create_token", "decode_token",
           "revoke_token", "is_revoked", "expire_seconds"]

_ITERATIONS = 120000  # PBKDF2 迭代次数：越高越慢但越难暴力破解
_PREFIX = "pbkdf2_sha256"  # 哈希串前缀，便于日后平滑更换算法
_revoked_tokens: set[str] = set()  # 已撤销令牌名单（进程内，服务重启后自然失效）


def hash_password(password: str) -> str:
    """生成加盐密码哈希串，格式 ``pbkdf2_sha256$迭代次数$盐$摘要``（PRD 2.7.14）。"""
    # 步骤 1：每个密码使用独立随机盐，避免相同密码产生相同哈希
    salt = secrets.token_hex(16)
    # 步骤 2：派生密钥并做 base64 编码后落库
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"),
                                 _ITERATIONS)
    return "%s$%d$%s$%s" % (_PREFIX, _ITERATIONS, salt, base64.b64encode(digest).decode("ascii"))


def verify_password(password: str, stored_hash: str | None) -> bool:
    """校验明文密码是否与存储的哈希匹配。"""
    # 步骤 1：解析哈希串，格式非法一律视为不匹配（不抛错，避免泄露内部结构）
    try:
        prefix, iterations, salt, expected = (stored_hash or "").split("$")
    except ValueError:
        return False
    if prefix != _PREFIX:
        return False
    # 步骤 2：用相同盐与迭代次数重算，并做恒定时间比较
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"),
                                 int(iterations))
    return hmac.compare_digest(base64.b64encode(digest).decode("ascii"), expected)


def expire_seconds() -> int:
    """返回令牌有效期（秒），供接口说明展示（PRD 13.10 要求明确令牌有效期）。"""
    return auth_config.expire_minutes * 60


def create_token(user_id: int, username: str, role_codes: list[str]) -> tuple[str, int]:
    """签发访问令牌，返回 (令牌, 有效期秒数)。"""
    # 步骤 1：校验密钥已配置——密钥缺失时签发无意义，直接报错而非静默签出无效令牌
    if not auth_config.secret_key:
        raise ValueError("未配置 JWT_SECRET_KEY，无法签发访问令牌")
    now = int(time.time())
    seconds = expire_seconds()
    # 步骤 2：载荷含主体、角色、签发时间、过期时间与唯一标识（jti 供撤销使用）
    payload = {
        "sub": str(user_id), "username": username, "roles": list(role_codes),
        "iat": now, "exp": now + seconds, "jti": secrets.token_hex(8),
    }
    token = jwt.encode(payload, auth_config.secret_key, algorithm=auth_config.algorithm)
    return token, seconds


def decode_token(token: str) -> dict | None:
    """解析并校验令牌；已撤销、过期或签名不符时返回 None。"""
    # 步骤 1：撤销名单优先——令牌即使仍在有效期内，被撤销后也一律失效（PRD 2.7.14）
    if token in _revoked_tokens:
        return None
    # 步骤 2：校验签名与过期时间
    try:
        return jwt.decode(token, auth_config.secret_key, algorithms=[auth_config.algorithm])
    except jwt.PyJWTError:
        return None


def revoke_token(token: str) -> None:
    """撤销令牌（PRD 2.7.14 撤销机制）。"""
    _revoked_tokens.add(token)


def is_revoked(token: str) -> bool:
    """查询令牌是否已被撤销。"""
    return token in _revoked_tokens
