"""Report context sanitization — mask sensitive data before storage/display."""
import re
import uuid
from datetime import datetime

SENSITIVE_KEY_PATTERNS = [
    re.compile(r'api[_-]?key', re.IGNORECASE),
    re.compile(r'secret', re.IGNORECASE),
    re.compile(r'token', re.IGNORECASE),
    re.compile(r'password', re.IGNORECASE),
    re.compile(r'authorization', re.IGNORECASE),
]

SENSITIVE_VALUE_PATTERNS = [
    re.compile(r'sk-[A-Za-z0-9]{16,}'),     # OpenAI-style keys
    re.compile(r'ghp_[A-Za-z0-9]{32,}'),     # GitHub tokens
    re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'), # base64-looking long strings
]

MAX_AI_TEXT_LENGTH = 500  # truncate long AI responses in snapshots


def sanitize_report_context(context: dict, edition: str = "customer") -> dict:
    """Sanitize ReportContext for storage in ReportArtifact.context_snapshot.

    - Masks API keys, tokens, secrets
    - Truncates long AI raw text
    - Removes email addresses
    - Removes internal file paths
    """
    if not context:
        return {}

    sanitized = _sanitize_value(copy_dict(context), depth=0, max_depth=5)
    return sanitized


def copy_dict(d: dict) -> dict:
    """Shallow-recursive copy of a dict."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = copy_dict(v)
        elif isinstance(v, list):
            result[k] = [
                copy_dict(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


def _sanitize_value(obj, depth: int, max_depth: int):
    """Recursively sanitize — mask sensitive keys, truncate long text, remove PII."""
    if depth > max_depth:
        return obj

    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if _is_sensitive_key(k):
                result[k] = "***REDACTED***"
            elif isinstance(v, str):
                result[k] = _sanitize_string(v)
            elif isinstance(v, (dict, list)):
                result[k] = _sanitize_value(v, depth + 1, max_depth)
            else:
                result[k] = v
        return result

    if isinstance(obj, list):
        return [_sanitize_value(item, depth + 1, max_depth) for item in obj]

    if isinstance(obj, str):
        return _sanitize_string(obj)

    return obj


def _is_sensitive_key(key: str) -> bool:
    return any(p.search(key) for p in SENSITIVE_KEY_PATTERNS)


def _sanitize_string(value: str) -> str:
    if not value:
        return value
    # Mask email
    value = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '***@***.***', value)
    # Mask sensitive-looking values
    for pat in SENSITIVE_VALUE_PATTERNS:
        value = pat.sub('***REDACTED***', value)
    # Mask file paths
    value = re.sub(r'(/[a-zA-Z0-9._-]+)+/[a-zA-Z0-9._-]+\.(py|json|yaml|yml|env|conf|key|pem)', '***PATH_REDACTED***', value)
    # Truncate long text
    if len(value) > MAX_AI_TEXT_LENGTH:
        value = value[:MAX_AI_TEXT_LENGTH] + "..."
    return value
