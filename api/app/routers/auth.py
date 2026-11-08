# ============================================================================
# auth.py — 认证与令牌端点（任务 3 的全部接口）
#
# 接口一览：
#   POST /api/v1/auth/register             注册（3.1）
#   POST /api/v1/auth/token                登录（3.1，契约 O-07）
#   POST /api/v1/auth/logout               登出并吊销令牌（3.2）
#   GET  /api/v1/auth/me                   获取当前用户（演示/客户端用）
#   POST /api/v1/auth/password-reset/request   请求找回验证码（3.3）
#   POST /api/v1/auth/password-reset/confirm   用验证码改密（3.3）
# ============================================================================
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import config, mail, schemas, security
from ..deps import CurrentUser, get_current_user

logger = logging.getLogger("gradebook.auth")
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# --------------------------- 工具函数 ---------------------------

async def _rate_limit(redis, key: str, limit: int, window: int) -> None:
    """基于 Redis 的简单滑动窗口限流（计数器 + 过期）。

    超过 limit 次则抛 429。用于登录/注册/找回，缓解暴力破解（TB-01 rate-limit）。
    """
    count = await redis.incr(key)          # 原子自增
    if count == 1:                          # 第一次请求：设置窗口过期时间
        await redis.expire(key, window)
    if count > limit:
        raise HTTPException(status_code=429, detail="Слишком много запросов. Попробуйте позже")


async def _generic_500(exc: Exception) -> HTTPException:
    """把未预期异常转为中性 500 响应（任务 4.5）。

    客户端只看到中性文案；真实异常与堆栈只写日志，不外泄给客户端。
    """
    logger.exception("необработанная ошибка")
    return HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


# --------------------------- 3.1 注册与登录 ---------------------------

@router.post("/register", response_model=schemas.UserOut, status_code=201)
async def register(body: schemas.RegisterRequest, request: Request):
    """注册新账号。

    - 角色由服务器强制为 student（客户端不能自选角色，防提权，TB-02）；
    - 邮箱唯一，重复返回 409；
    - 密码以 Argon2id+pepper 哈希后入库。
    """
    redis = request.app.state.redis
    pool = request.app.state.pool
    client_ip = request.client.host if request.client else "unknown"
    try:
        await _rate_limit(redis, f"rl:register:{client_ip}", config.LOGIN_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)

        # 邮箱唯一性：先查后插，同时靠数据库 UNIQUE 约束兜底
        exists = await pool.fetchval("SELECT 1 FROM users WHERE email = $1", body.email)
        if exists:
            raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")

        password_hash, password_salt = security.hash_password(body.password)
        user_id = await pool.fetchval(
            "INSERT INTO users (email, role, password_hash, password_salt) "
            "VALUES ($1, $2, $3, $4) RETURNING id",
            body.email, "student", password_hash, password_salt,
        )
        return schemas.UserOut(id=str(user_id), email=body.email, role="student")
    except HTTPException:
        raise
    except Exception as exc:
        raise await _generic_500(exc)


@router.post("/token", response_model=schemas.TokenResponse)
async def login(body: schemas.LoginRequest, request: Request):
    """登录（契约 O-07 /api/v1/auth/token）。

    安全要点：
    - 邮箱不存在与密码错误返回完全相同的 401（不泄露账号是否存在）；
    - 邮箱不存在时也执行一次等量哈希（抹平时序差异，防枚举）；
    - 登录成功后在 Redis 写入会话 allowlist 记录（令牌吊销的基础）；
    - 按 IP 与邮箱限流。
    """
    redis = request.app.state.redis
    pool = request.app.state.pool
    client_ip = request.client.host if request.client else "unknown"
    try:
        # 限流（防止暴力破解登录）
        await _rate_limit(redis, f"rl:login:{client_ip}", config.LOGIN_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)
        await _rate_limit(redis, f"rl:login:{body.email}", config.LOGIN_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)

        row = await pool.fetchrow(
            "SELECT id, email, role, password_hash, password_salt FROM users WHERE email = $1",
            body.email,
        )
        if row is None:
            # 用户不存在：做一次等量哈希，让响应耗时与“密码错误”一致
            security.timing_equalize_work()
            raise HTTPException(status_code=401, detail="Неверный email или пароль")

        if not security.verify_password(body.password, row["password_hash"], row["password_salt"]):
            raise HTTPException(status_code=401, detail="Неверный email или пароль")

        # 签发令牌并解码出 jti/有效期，用于写会话 allowlist
        token = security.create_access_token(row["id"], row["role"])
        payload = security.decode_token(token)
        ttl = payload["exp"] - payload["iat"]
        # 会话记录：sess:{user_id}:{jti}，TTL 与令牌一致 —— 到期自动失效
        await redis.set(f"sess:{row['id']}:{payload['jti']}", row["role"], ex=ttl)

        return schemas.TokenResponse(access_token=token, token_type="bearer", expires_in=ttl)
    except HTTPException:
        raise
    except Exception as exc:
        raise await _generic_500(exc)


# --------------------------- 3.2 令牌与登出 ---------------------------

@router.post("/logout", status_code=204)
async def logout(user: CurrentUser = Depends(get_current_user), request: Request = None):
    """登出：删除 Redis 中的会话记录，令牌即刻失效（真正吊销）。

    此后该令牌再访问任何受保护端点都会被 401 拒绝。
    """
    redis = request.app.state.redis
    await redis.delete(f"sess:{user.id}:{user.jti}")
    # 204 无响应体


@router.get("/me", response_model=schemas.UserOut)
async def me(user: CurrentUser = Depends(get_current_user)):
    """返回当前用户信息（仅 id/email/role，绝不返回密码哈希）。

    用于客户端展示与答辩演示令牌认证是否生效。
    """
    return schemas.UserOut(id=str(user.id), email=user.email, role=user.role)


# --------------------------- 3.3 找回密码 ---------------------------

@router.post("/password-reset/request", response_model=schemas.MessageOut)
async def password_reset_request(body: schemas.ResetRequest, request: Request):
    """找回密码第一步：请求一次性验证码。

    - 无论邮箱是否存在都返回同一提示（防账号枚举）；
    - 只有用户存在时才生成验证码并写入 Redis（hash 形式，TTL 15 分钟）并发送邮件；
    - 再次请求会覆盖旧验证码（同一时刻只允许一个有效）。
    """
    redis = request.app.state.redis
    pool = request.app.state.pool
    client_ip = request.client.host if request.client else "unknown"
    try:
        await _rate_limit(redis, f"rl:reset:{client_ip}", config.LOGIN_RATE_LIMIT, config.RATE_LIMIT_WINDOW_SECONDS)

        user_id = await pool.fetchval("SELECT id FROM users WHERE email = $1", body.email)
        if user_id:
            code = security.generate_reset_code()
            # 只存验证码的哈希，TTL = 有效期
            await redis.setex(
                f"pwreset:{body.email}",
                config.RESET_CODE_TTL_MINUTES * 60,
                security.hash_code(code),
            )
            await mail.send_reset_code(body.email, code)

        return schemas.MessageOut(message="Если пользователь существует, код отправлен на email")
    except HTTPException:
        raise
    except Exception as exc:
        raise await _generic_500(exc)


@router.post("/password-reset/confirm", response_model=schemas.MessageOut)
async def password_reset_confirm(body: schemas.ResetConfirm, request: Request):
    """找回密码第二步：用一次性验证码设置新密码。

    - 验证码只能使用一次：成功后立即删除 Redis 记录（过期/已用 → 400）；
    - 成功后重置该用户全部会话（改密即登出所有设备）；
    - 新密码同样以 Argon2id+pepper 哈希入库。
    """
    redis = request.app.state.redis
    pool = request.app.state.pool
    try:
        key = f"pwreset:{body.email}"
        stored_hash = await redis.get(key)
        if not stored_hash or not security.verify_code(body.code, stored_hash):
            raise HTTPException(status_code=400, detail="Неверный или истёкший код")

        row = await pool.fetchrow("SELECT id FROM users WHERE email = $1", body.email)
        if row is None:
            raise HTTPException(status_code=400, detail="Пользователь не найден")

        # 更新密码（新盐、新哈希）
        password_hash, password_salt = security.hash_password(body.new_password)
        await pool.execute(
            "UPDATE users SET password_hash = $1, password_salt = $2 WHERE id = $3",
            password_hash, password_salt, row["id"],
        )

        # 一次性：删除验证码
        await redis.delete(key)

        # 吊销该用户所有会话（sess:{user_id}:*）
        async for session_key in redis.scan_iter(match=f"sess:{row['id']}:*"):
            await redis.delete(session_key)

        return schemas.MessageOut(message="Пароль изменён")
    except HTTPException:
        raise
    except Exception as exc:
        raise await _generic_500(exc)
