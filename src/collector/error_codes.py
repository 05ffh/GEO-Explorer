"""Standard error codes for collector engine — no string matching in dispatch logic."""
from enum import Enum


class CollectorErrorCode(str, Enum):
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    AUTH_ERROR = "auth_error"
    INVALID_CONFIG = "invalid_config"
    EMPTY_RESPONSE = "empty_response"
    CONTENT_FILTERED = "content_filtered"
    QUOTA_EXCEEDED = "quota_exceeded"
    NETWORK_ERROR = "network_error"
    PARSE_ERROR = "parse_error"
    CIRCUIT_OPEN = "circuit_open"
    BUDGET_EXCEEDED = "budget_exceeded"
    CANCELLED = "cancelled"
    UNKNOWN_ERROR = "unknown_error"


RETRYABLE_ERRORS = {
    CollectorErrorCode.RATE_LIMIT,
    CollectorErrorCode.TIMEOUT,
    CollectorErrorCode.SERVER_ERROR,
    CollectorErrorCode.NETWORK_ERROR,
    CollectorErrorCode.CIRCUIT_OPEN,
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
            return CollectorErrorCode.UNKNOWN_ERROR
    return None


def to_code(code) -> str:
    """Convert string or enum to string for DB storage."""
    if code is None:
        return ""
    if isinstance(code, CollectorErrorCode):
        return code.value
    return str(code)
