"""Manual retry strategy — no autoretry_for, explicit classify_error + self.retry."""
import random
import logging

logger = logging.getLogger(__name__)

RETRYABLE_ERRORS = {
    "RateLimitError",
    "ConnectionError",
    "TimeoutError",
    "DatabaseLockError",
    "RedisConnectionError",
}

NON_RETRYABLE_ERRORS = {
    "ValidationError",
    "BrandNotFoundError",
    "ConfigurationError",
    "AuthenticationError",
}

RETRY_BACKOFF_BASE = 60
RETRY_BACKOFF_MAX = 3600


def classify_error(exc: Exception) -> tuple[str, str]:
    """Return (error_type, retry_policy).

    retry_policy:
      - "retry": retryable, use self.retry with backoff
      - "dlq_manual": unknown error, DLQ with manual review
      - "dlq_never": permanent error, DLQ with never retry
    """
    exc_name = type(exc).__name__
    if exc_name in RETRYABLE_ERRORS:
        return exc_name, "retry"
    if exc_name in NON_RETRYABLE_ERRORS:
        return exc_name, "dlq_never"
    return exc_name, "dlq_manual"


def get_retry_delay(retry_count: int) -> int:
    """Exponential backoff: 60 -> 120 -> 240 -> 480 ... capped at 3600s, ±50% jitter."""
    base = min(RETRY_BACKOFF_BASE * (2 ** retry_count), RETRY_BACKOFF_MAX)
    delay = int(base * (0.5 + random.random()))
    delay = min(delay, RETRY_BACKOFF_MAX)  # hard cap at max
    return max(delay, 10)
