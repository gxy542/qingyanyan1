# ============================================================================
# db.py — PostgreSQL 连接池
# 作用：创建 asyncpg 连接池，供各处理函数取连接执行参数化查询。
# 说明：应用用 app_api 角色连接（见 roles.sql），只有 CRUD 权限、没有 DDL 权限。
# ============================================================================
import asyncpg

from . import config


async def create_pool() -> asyncpg.Pool:
    """启动时创建数据库连接池。min_size=1 保证一直有可用连接。"""
    return await asyncpg.create_pool(
        dsn=config.DATABASE_URL,
        min_size=1,
        max_size=10,
    )
