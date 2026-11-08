# ============================================================================
# deps.py — 认证依赖（任务 3.2 的“吊销检查”在这里）
# 作用：把「当前用户」作为 FastAPI 依赖注入到各受保护端点。
# 流程：从 Authorization 头取 Bearer 令牌 → 验签/过期(decode_token) → 查 Redis
#       会话 allowlist（sess:{user_id}:{jti}）确认未被吊销 → 查库确认用户仍在。
# 任何一步失败都统一返回 401。
# ============================================================================
import uuid

from fastapi import Depends, HTTPException, Request

from . import security
from .db import create_pool  # 仅类型提示用途


class CurrentUser:
    """通过认证后的当前用户上下文（含令牌 jti，供登出吊销用）。"""

    def __init__(self, id, email: str, role: str, jti: str):
        self.id = id
        self.email = email
        self.role = role
        self.jti = jti


_UNAUTHORIZED = HTTPException(status_code=401, detail="Недостаточно прав или неверный токен")


async def get_current_user(request: Request) -> CurrentUser:
    """从请求头解析令牌并做完整认证。任何异常都抛 401。"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise _UNAUTHORIZED                       # 缺少或错误的授权头

    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = security.decode_token(token)     # 验签 + 检查过期/类型
    except security.TokenError:
        raise _UNAUTHORIZED from None

    user_id = payload["sub"]
    jti = payload["jti"]
    redis = request.app.state.redis
    db_pool = request.app.state.pool

    # 会话 allowlist 检查：令牌必须对应一条 Redis 中仍存在的会话记录。
    # 登出/吊销会删除该记录，因此被吊销或已登出的令牌在此处返回 401。
    if not await redis.exists(f"sess:{user_id}:{jti}"):
        raise _UNAUTHORIZED

    # 确认用户仍存在（被删除的账号令牌同样失效）
    row = await db_pool.fetchrow(
        "SELECT id, email, role FROM users WHERE id = $1", uuid.UUID(user_id)
    )
    if row is None:
        raise _UNAUTHORIZED

    return CurrentUser(id=row["id"], email=row["email"], role=row["role"], jti=jti)


def require_role(*roles: str):
    """返回一个依赖：要求当前用户角色属于 roles，否则 403。

    这是 RBAC（任务 4 中用于特权端点）的复用基础。
    """
    async def _checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав для операции")
        return user
    return _checker
