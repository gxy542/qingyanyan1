# ============================================================================
# mail.py — 本地邮件桩（任务 3.3）
# 作用：把找回密码验证码通过 SMTP 发送到本地 Mailpit（容器 C-10 的桩实现）。
# 失败时回退为写日志，保证邮件桩不可用不阻断主流程（对应 G-06）。
# ============================================================================
import logging
from email.message import EmailMessage

import aiosmtplib

from . import config

logger = logging.getLogger("gradebook.mail")


async def send_reset_code(email: str, code: str) -> None:
    """给指定邮箱发送一次性验证码（经 Mailpit 本地桩）。

    - subject/body 只含验证码与有效期，不含其它个人/学业敏感信息（M-05 缓解）；
    - 用 EmailMessage 构造，正文字符集声明为 UTF-8，避免西里尔字母
      被按 ASCII 编码而抛 UnicodeEncodeError；
    - Mailpit 网页收件箱：http://localhost:8025。
    """
    # 构造符合 MIME 规范的邮件（标准库，不依赖额外包）
    message = EmailMessage()
    message["From"] = config.MAIL_FROM
    message["To"] = email
    message["Subject"] = "Сброс пароля — Журнал оценок"
    body = (
        f"Ваш одноразовый код для сброса пароля: {code}\n"
        f"Код действует {config.RESET_CODE_TTL_MINUTES} минут.\n"
    )
    # set_content 自动加 Content-Type: text/plain; charset=utf-8
    message.set_content(body)

    try:
        # 用 EmailMessage 时 aiosmtplib 会自行从邮件头取发件人/收件人，
        # 并按声明的 UTF-8 编码正文。
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
