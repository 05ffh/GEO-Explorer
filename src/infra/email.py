"""Email service abstraction — pluggable backends (SMTP / SendGrid / Mailgun / SES)."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailBackend(Protocol):
    async def send(self, to: str, subject: str, html_body: str) -> dict:
        ...


class MockEmailBackend:
    """Dev backend: log emails instead of sending."""
    async def send(self, to: str, subject: str, html_body: str) -> dict:
        logger.info(f"[MockEmail] To: {to} | Subject: {subject}")
        return {"sent": True, "mock": True, "message_id": str(uuid.uuid4())}


class SmtpEmailBackend:
    """SMTP backend for production."""
    def __init__(self, host: str, port: int, user: str, password: str, from_addr: str):
        self.host = host; self.port = port
        self.user = user; self.password = password
        self.from_addr = from_addr

    async def send(self, to: str, subject: str, html_body: str) -> dict:
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        msg["From"] = self.from_addr
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg, hostname=self.host, port=self.port,
            username=self.user, password=self.password,
            use_tls=self.port == 465, start_tls=self.port == 587,
        )
        return {"sent": True, "message_id": str(uuid.uuid4())}


def get_email_backend() -> EmailBackend:
    """Factory: return the configured email backend."""
    from src.config import settings
    provider = getattr(settings, "email_provider", "mock")
    if provider == "mock" or settings.app_env == "development":
        return MockEmailBackend()
    if provider == "smtp":
        return SmtpEmailBackend(
            host=settings.smtp_host, port=settings.smtp_port,
            user=settings.smtp_user, password=settings.smtp_password,
            from_addr=settings.email_from,
        )
    # TODO: SendGrid / Mailgun / SES backends
    logger.warning(f"Unknown email provider {provider}, using mock")
    return MockEmailBackend()


def generate_verification_token(email: str) -> str:
    raw = f"{email}:{uuid.uuid4().hex}:{datetime.now(timezone.utc).timestamp()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def send_verification_email(email: str, token: str):
    """Send email verification link. Store token hash, not raw token."""
    backend = get_email_backend()
    from src.config import settings
    base = settings.app_base_url.rstrip("/")
    link = f"{base}/api/auth/verify-email?token={token}"
    return await backend.send(email, "验证你的邮箱 — GEO Explorer",
        f'<p>点击验证你的邮箱：<a href="{link}">验证邮箱</a></p>'
        f'<p>链接 24 小时内有效。</p>')


async def send_invite_email(email: str, org_name: str, accept_url: str):
    backend = get_email_backend()
    return await backend.send(email, f"加入 {org_name} — GEO Explorer",
        f'<p>你被邀请加入 <strong>{org_name}</strong>。</p>'
        f'<p><a href="{accept_url}">接受邀请</a></p>'
        f'<p>链接 7 天内有效。</p>')
