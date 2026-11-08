# ============================================================================
# main.py — FastAPI 应用入口
# 作用：组装应用；启动时初始化数据库连接池、Redis、播种测试用户；挂载认证路由。
# ============================================================================
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config, db, redis_client, seed
from .routers import admin, auth, courses, grades, retake

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时准备依赖，关闭时释放资源。"""
    # 校验关键密钥（没有 JWT_SECRET / PASSWORD_PEPPER 则直接报错退出）
    config.validate_required_secrets()

    # 建立数据库连接池与 Redis 客户端，挂到 app.state 供各处使用
    app.state.pool = await db.create_pool()
    app.state.redis = await redis_client.create_redis()

    # 播种测试用户 + 课程/选课/成绩演示数据，保证 up 之后可直接演示
    await seed.seed_all(app.state.pool)

    logging.info("系统已就绪：http://localhost:8000/docs")

    yield  # 应用运行期间

    # 关闭时清理资源
    await app.state.redis.aclose()
    await app.state.pool.close()


# 创建应用
app = FastAPI(
    title="Журнал для оценки обучающихся — API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS：只允许白名单来源（不从代码里直接放开“所有来源”）
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载认证与令牌路由
app.include_router(auth.router)
# 任务 4：按 ЛР2 契约挂载业务路由
app.include_router(grades.router)
app.include_router(retake.router)
app.include_router(courses.router)
app.include_router(admin.router)

# 前端静态页面（web/index.html）。容器内挂载在 /app/web。
# 放在最后挂载：/api/v1/... 路由优先命中，其余路径回落到静态页。
_web_dir = Path("/app/web")
if _web_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")
