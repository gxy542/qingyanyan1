# ============================================================================
# redis_client.py — Redis 客户端（容器 C-07：会话与限流）
# 作用：创建全局 Redis 异步客户端。decode_responses=True 让返回的是字符串而非字节。
# 本任务里 Redis 承担三类职责：
#   sess:{user_id}:{jti}  会话 allowlist（令牌吊销，任务 3.2）
#   pwreset:{email}       一次性找回密码验证码（任务 3.3）
#   rl:...                登录/注册限流计数（TB-01）
# ============================================================================
import redis.asyncio as aioredis

from . import config


async def create_redis() -> aioredis.Redis:
    """启动时创建 Redis 客户端。"""
    return aioredis.from_url(config.REDIS_URL, decode_responses=True)
