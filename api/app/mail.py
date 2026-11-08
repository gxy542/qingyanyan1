# ============================================================================
# mail.py — 本地邮件桩（任务 3.3）
# 作用：把找回密码验证码通过 SMTP 发送到本地 Mailpit（容器 C-10 的桩实现）。
# 失败时回退为写日志，保证邮件桩不可用不阻断主流程（对应 G-06）。
# ============================================================================
import logging

import aiosmtplib

from . import config

logger = logging.getLogger("gradebook.mail")


async def send_reset_code(email: str, code: str) -> None:
    """给指定邮箱发送一次性验证码（经 Mailpit 本地桩）。

    - subject/body 只含验证码与有效期，不含其它个人/学业敏感信息（M-05 缓解）。
    - Mailpit 网页收件箱：http://localhost:8025
    """
    subject = "Сброс пароля — Журнал оценок"
    body = (
        f"Ваш одноразовый код для сброса пароля: {code}\n"
        f"Код действует {config.RESET_CODE_TTL_MINUTES} минут.\n"
    )
    # 构造最小 SMTP 数据（头部 + 正文）
    message = (
        f"From: {config.MAIL_FROM}\r\n"
        f"To: {email}\r\n"
        f"Subject: {subject}\r\n"
        f"\r\n"
        f"{body}"
    )
    try:
        await aiosmtplib.send(
            message,
            hostname=config.MAIL_HOST,
            port=config.MAIL_PORT,
            timeout=5,
        )
    except Exception:
        # 桩不可用或网络问题：记录日志并继续（不丢失业务操作）
        logger.exception("邮件桩不可用，验证码改由日志输出")
        logger.warning("RESET CODE for %s: %s", email, code)
