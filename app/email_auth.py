import hashlib
import hmac
import logging
import secrets

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


def create_email_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_email_code(email: str, code: str) -> str:
    secret = get_settings().secret_key.encode()
    message = f"{email}:{code}".encode()
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def send_email_login_code(email: str, code: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key or not settings.email_from:
        raise RuntimeError("Email login is not configured")

    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.email_from,
                "to": [email],
                "subject": "拾集登录验证码",
                "html": (
                    f"<p>你的拾集登录验证码是：</p>"
                    f"<p style=\"font-size:28px;font-weight:bold;letter-spacing:8px\">{code}</p>"
                    "<p>验证码 10 分钟内有效。如非本人操作，请忽略此邮件。</p>"
                ),
            },
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        logger.warning("Resend email request failed: %s", type(error).__name__)
        raise RuntimeError("Email provider request failed") from None
