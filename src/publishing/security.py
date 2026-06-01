"""Publishing security — SSRF protection, HMAC signing, URL validation, credential redaction (P2-4)."""
import hashlib
import hmac
import ipaddress
import logging
import re
import secrets
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Private/loopback networks
SSRF_BLOCKED_NETWORKS = [
    ipaddress.IPv4Network("127.0.0.0/8"),
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
    ipaddress.IPv4Network("169.254.0.0/16"),
    ipaddress.IPv6Network("::1/128"),
    ipaddress.IPv6Network("fc00::/7"),
    ipaddress.IPv6Network("fe80::/10"),
]


def validate_webhook_url(url: str) -> tuple[bool, str]:
    """Validate a webhook URL for SSRF safety. Returns (is_valid, error_message)."""
    if not url:
        return False, "URL 不能为空"

    parsed = urlparse(url)

    if parsed.scheme != "https":
        return False, "仅允许 HTTPS"

    if parsed.hostname is None:
        return False, "无法解析主机名"

    hostname = parsed.hostname.lower()
    if hostname in ("localhost", "127.0.0.1", "::1"):
        return False, "不允许 localhost"

    # DNS rebinding check: blocked IPs
    try:
        from socket import getaddrinfo, AF_INET, AF_INET6
        for family in (AF_INET, AF_INET6):
            try:
                for info in getaddrinfo(hostname, None, family):
                    ip_str = info[4][0]
                    ip = ipaddress.ip_address(ip_str)
                    if ip.is_loopback or ip.is_private or ip.is_link_local:
                        return False, f"不允许内网地址: {ip_str}"
                    for net in SSRF_BLOCKED_NETWORKS:
                        if ip in net:
                            return False, f"不允许内网地址: {ip_str}"
            except Exception:
                pass
    except Exception:
        return False, "DNS 解析失败"

    return True, ""


def validate_asset_url(url: str) -> tuple[bool, str]:
    """Validate an asset URL for SSRF safety."""
    if not url:
        return False, "asset URL 不能为空"
    if not url.startswith("https://"):
        return False, "asset URL 仅允许 HTTPS"
    return validate_webhook_url(url)


def compute_hmac_signature(payload: bytes, secret: str, timestamp: str) -> str:
    """Compute HMAC-SHA256 signature for webhook delivery."""
    message = payload + timestamp.encode()
    mac = hmac.new(secret.encode(), message, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def verify_hmac_signature(payload: bytes, secret: str, timestamp: str, signature: str) -> bool:
    """Verify an incoming HMAC-SHA256 signature."""
    expected = compute_hmac_signature(payload, secret, timestamp)
    return hmac.compare_digest(expected, signature)


def generate_webhook_secret() -> str:
    """Generate a webhook secret. Returns raw secret (show once, hash for DB)."""
    return secrets.token_hex(32)


def hash_secret(secret: str) -> str:
    """Hash a webhook secret for storage."""
    return hashlib.sha256(secret.encode()).hexdigest()


def generate_callback_token() -> tuple[str, str]:
    """Generate a callback token. Returns (raw_token, hash)."""
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def verify_callback_timestamp(ts: int, window_seconds: int = 300) -> bool:
    """Verify callback timestamp is within the allowed window."""
    from datetime import datetime, timezone
    now = int(datetime.now(timezone.utc).timestamp())
    return abs(now - ts) <= window_seconds


def mask_url(url: str) -> str:
    """Mask a URL for safe display. Shows scheme+host, masks path params."""
    if not url:
        return ""
    parsed = urlparse(url)
    path = parsed.path or ""
    if len(path) > 20:
        path = path[:20] + "***"
    return f"{parsed.scheme}://{parsed.hostname}{path}"


def mask_credential(value: str) -> str:
    """Mask a credential value. Shows first 2 + last 2 chars."""
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return value[:2] + "****" + value[-2:]


def redact_publish_payload(payload: dict) -> dict:
    """Redact sensitive fields from a publish payload for logging."""
    safe = dict(payload)
    cb = safe.get("callback", {})
    if isinstance(cb, dict) and "callback_token" in cb:
        cb = dict(cb)
        cb["callback_token"] = "***REDACTED***"
        safe["callback"] = cb
    content = safe.get("content", {})
    if isinstance(content, dict):
        content = dict(content)
        body = content.get("body_html", "")
        if len(body) > 500:
            content["body_html"] = body[:500] + "...[truncated]"
        safe["content"] = content
    return safe


def redact_response_body(text: str, max_len: int = 500) -> str:
    """Redact and truncate a response body for safe storage."""
    if not text:
        return ""
    # Strip common sensitive patterns
    text = re.sub(r'(Authorization|Bearer|X-API-Key):\s*[^\r\n]+', r'\1: ***REDACTED***', text, flags=re.IGNORECASE)
    if len(text) > max_len:
        text = text[:max_len] + "...[truncated]"
    return text
