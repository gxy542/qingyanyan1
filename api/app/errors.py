# ============================================================================
# errors.py — 统一错误处理（任务 4.5）
# 作用：把未预期异常转成中性 500 响应；真实异常与堆栈只写日志，绝不外泄给客户端，
#       也不把 SQL/堆栈文本返回。所有业务端点共用。
# ============================================================================
import logging

from fastapi import HTTPException

logger = logging.getLogger("gradebook.errors")


async def internal_error(exc: Exception) -> HTTPException:
    """记录真实异常（含堆栈）到日志，并返回中性 500 给客户端。"""
    logger.exception("необработанная ошибка")
    return HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
