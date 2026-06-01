"""Data sanitization for task payloads — mask sensitive fields."""
import re

SENSITIVE_KEYS = {
    "api_key", "api_secret", "token", "secret", "password",
    "authorization", "access_token", "refresh_token", "private_key",
    "key", "secret_key", "apikey",
}


def sanitize_dict(data: dict | None, max_depth: int = 3) -> dict | None:
    """Recursively mask sensitive values in a dict."""
    if data is None:
        return None
    if max_depth <= 0:
        return data
    result = {}
    for k, v in data.items():
        if k.lower() in SENSITIVE_KEYS or _looks_like_api_key(str(v)):
            result[k] = "***REDACTED***"
        elif isinstance(v, dict):
            result[k] = sanitize_dict(v, max_depth - 1)
        elif isinstance(v, list):
            result[k] = [
                sanitize_dict(item, max_depth - 1) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


def sanitize_list(data: list | None) -> list | None:
    """Mask sensitive values in a list of dicts/strings."""
    if data is None:
        return None
    result = []
    for item in data:
        if isinstance(item, dict):
            result.append(sanitize_dict(item))
        elif isinstance(item, str) and _looks_like_api_key(item):
            result.append("***REDACTED***")
        else:
            result.append(item)
    return result


def _looks_like_api_key(value: str) -> bool:
    """Heuristic: strings that look like API keys."""
    if not value or len(value) < 8:
        return False
    # Common patterns: sk-..., ghp_..., ak-..., long base64-like strings
    if re.match(r'^(sk-|ghp_|ak-|pk\.)', value):
        return True
    if len(value) >= 32 and re.match(r'^[A-Za-z0-9_\-\.]{32,}$', value):
        return True
    return False
