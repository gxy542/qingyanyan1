# ============================================================================
# security.py — 密码哈希与 JWT 令牌（任务 3.1 与 3.2 的核心）
#
# 3.1 密码：Argon2id（ЛР2 指定）+ 每用户随机盐 + pepper（来自环境变量）。
#      采用「先拼 pepper 再哈希」；盐存 password_salt 列，pepper 只在环境变量里。
# 3.2 令牌：JWT(HS256)。载荷含 sub(用户id)、role、type、jti(唯一ID)、iat、exp。
#      伪造/过期由签名与 exp 拒绝；吊销由 Redis 会话 allowlist 完成（见 deps.py）。
# ============================================================================
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import argon2.low_level as argon2_ll   # Argon2 底层接口，允许我们自定义盐
import jwt

from . import config


# ============================ 3.1 密码哈希 ============================

def _argon2id_hash(raw: bytes, salt: bytes) -> str:
    """对指定字节串做 Argon2id 哈希，返回可存储的编码串（含算法版本与成本参数）。

    使用 argon2 底层接口，以便把「我们生成的盐」写进 password_salt 列。
    相同 (明文,盐,参数) 的输出是确定的，因此校验时可重新计算后比较。
    """
    return argon2_ll.hash_secret(
        secret=raw,
        salt=salt,
        time_cost=config.ARGON2_TIME_COST,
        memory_cost=config.ARGON2_MEMORY_COST,   # 单位 KiB
        parallelism=config.ARGON2_PARALLELISM,
        hash_len=config.ARGON2_HASH_LEN,
        type=argon2_ll.Type.ID,
        version=19,
    ).decode("ascii")


def hash_password(password: str) -> tuple[str, str]:
    """生成 (password_hash, password_salt)。

    - 先把密码与 pepper 拼接（pepper 只存在环境变量，不落库）；
    - 生成 16 字节加密随机盐；
    - 做 Argon2id 哈希。返回的盐以十六进制存库，供校验时复现。
    """
    peppered = (password + config.PASSWORD_PEPPER).encode("utf-8")
    salt = secrets.token_bytes(16)                 # 每用户唯一随机盐
    encoded = _argon2id_hash(peppered, salt)
    return encoded, salt.hex()


def verify_password(password: str, password_hash: str, password_salt_hex: str) -> bool:
    """校验密码：用同一 pepper 与库中盐重新计算哈希，再与库中哈希比对。

    采用常数时间比较 secrets.compare_digest，降低时序攻击风险。
    注意：验证使用的是「确定性重算」，而非 argon2 的 verify —— 更易解释且行为一致。
    """
    peppered = (password + config.PASSWORD_PEPPER).encode("utf-8")
    salt = bytes.fromhex(password_salt_hex)        # 从库中读出盐
    candidate = _argon2id_hash(peppered, salt)     # 用相同参数重算
    return secrets.compare_digest(candidate, password_hash)


# 用于「用户不存在时也执行一次哈希」的占位盐，抹平登录时序差异（防用户枚举）
_DUMMY_SALT = "00" * 16


def timing_equalize_work() -> None:
    """当邮箱不存在时调用，执行一次等量哈希计算，使响应耗时与「密码错误」接近。"""
    _argon2id_hash(b"timing", bytes.fromhex(_DUMMY_SALT))


# ============================ 3.2 JWT 令牌 ============================

class TokenError(Exception):
    """令牌无效/过期/伪造/已吊销时抛出的统一异常。"""


def create_access_token(user_id, role: str) -> str:
    """签发访问令牌（JWT HS256）。

    载荷说明：
      sub  —— 用户 ID（令牌的唯一所有者）
      role —— 角色，供 RBAC 使用
      type —— 'access'，预留刷新令牌等类型区分
      jti  —— 一次性随机 ID，作为 Redis 会话 allowlist 的键（实现吊销）
      iat  —— 签发时间
      exp  —— 过期时间（= 现在 + 有效期）
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=config.ACCESS_TOKEN_TTL_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """验签并解码令牌。伪造签名、过期、算法不匹配都会抛出 TokenError。

    流程：
      1) jwt.decode 校验签名与 exp（此时已能拒绝伪造/过期令牌）；
      2) 校验 type 必须是 access，防止其它类型令牌被误用。
    """
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError as exc:                  # 签名错 / 过期 / 格式错 等
        raise TokenError("недействительный или просроченный токен") from exc

    if payload.get("type") != "access":
        raise TokenError("недопустимый тип токена")
    return payload


# ============================ 3.3 一次性验证码 ============================

def generate_reset_code() -> str:
    """生成 6 位数字的一次性找回密码验证码。"""
    return f"{secrets.randbelow(10 ** config.RESET_CODE_LENGTH):06d}"


def hash_code(code: str) -> str:
    """对验证码做 SHA-256。Redis 里只存哈希、不存明文验证码。"""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def verify_code(code: str, stored_hash: str) -> bool:
    """校验验证码：重算哈希并与库中哈希常数时间比较。"""
    return secrets.compare_digest(hash_code(code), stored_hash)
