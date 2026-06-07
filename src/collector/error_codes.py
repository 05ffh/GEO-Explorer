"""Standard error codes for collector engine — no string matching in dispatch logic."""

from enum import Enum


class CollectorErrorCode(str, Enum):
    # Platform errors
    PLATFORM_RATE_LIMITED = "platform_rate_limited"   # 429
    PLATFORM_TIMEOUT = "platform_timeout"
    PLATFORM_AUTH_FAILED = "platform_auth_failed"
    PLATFORM_QUOTA_EXHAUSTED = "platform_quota_exhausted"
    PLATFORM_EMPTY_RESPONSE = "platform_empty_response"
    PLATFORM_PARSE_FAILED = "platform_parse_failed"
    PLATFORM_UNKNOWN_ERROR = "platform_unknown_error"

    # Legacy aliases (keep backward compat)
    RATE_LIMIT = "platform_rate_limited"
    TIMEOUT = "platform_timeout"
    AUTH_ERROR = "platform_auth_failed"
    QUOTA_EXCEEDED = "platform_quota_exhausted"
    EMPTY_RESPONSE = "platform_empty_response"
    PARSE_ERROR = "platform_parse_failed"
    UNKNOWN_ERROR = "platform_unknown_error"

    # Infrastructure errors
    SERVER_ERROR = "server_error"
    INVALID_CONFIG = "invalid_config"
    CONTENT_FILTERED = "content_filtered"
    NETWORK_ERROR = "network_error"
    CIRCUIT_OPEN = "circuit_open"
    BUDGET_EXCEEDED = "budget_exceeded"
    CANCELLED = "cancelled"


RETRYABLE_ERRORS = {
    CollectorErrorCode.PLATFORM_RATE_LIMITED,
    CollectorErrorCode.PLATFORM_TIMEOUT,
    CollectorErrorCode.SERVER_ERROR,
    CollectorErrorCode.NETWORK_ERROR,
    CollectorErrorCode.CIRCUIT_OPEN,
}


NON_RETRYABLE_ERRORS = {
    CollectorErrorCode.PLATFORM_AUTH_FAILED,
    CollectorErrorCode.PLATFORM_QUOTA_EXHAUSTED,
    CollectorErrorCode.INVALID_CONFIG,
    CollectorErrorCode.CONTENT_FILTERED,
    CollectorErrorCode.BUDGET_EXCEEDED,
    CollectorErrorCode.CANCELLED,
}


def is_retryable(code: CollectorErrorCode | None) -> bool:
    return code in RETRYABLE_ERRORS


def normalize_error_code(code) -> CollectorErrorCode | None:
    """Normalize string or enum to CollectorErrorCode. Returns None for None/empty."""
    if code is None:
        return None
    if isinstance(code, CollectorErrorCode):
        return code
    if isinstance(code, str) and code:
        try:
            return CollectorErrorCode(code)
        except ValueError:
            return CollectorErrorCode.PLATFORM_UNKNOWN_ERROR
    return None


def to_code(code) -> str:
    """Convert string or enum to string for DB storage."""
    if code is None:
        return ""
    if isinstance(code, CollectorErrorCode):
        return code.value
    return str(code)
