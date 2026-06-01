"""Mock email service for E2E tests."""
import logging

logger = logging.getLogger(__name__)

_sent_emails: list[dict] = []


def send_verification_email(email: str, token: str) -> dict:
    """Mock: record the email instead of sending."""
    _sent_emails.append({"to": email, "token": token, "type": "verification"})
    logger.info(f"Mock email to {email}: verification token={token}")
    return {"sent": True, "mock": True}


def send_invite_email(email: str, invite_token: str, org_name: str) -> dict:
    """Mock: record the invite email."""
    _sent_emails.append({"to": email, "token": invite_token, "org": org_name, "type": "invite"})
    return {"sent": True, "mock": True}


def get_sent_emails(to: str = "") -> list[dict]:
    """Get all recorded mock emails, optionally filtered by recipient."""
    if to:
        return [e for e in _sent_emails if e["to"] == to]
    return list(_sent_emails)


def clear_emails():
    """Clear mock email history."""
    _sent_emails.clear()
