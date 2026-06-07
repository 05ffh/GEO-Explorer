"""Search error classification types for GT Search pipeline."""

from dataclasses import dataclass
from enum import StrEnum


class SearchErrorKind(StrEnum):
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    PARSE_FAILED = "parse_failed"
    PROVIDER_DISABLED = "provider_disabled"


@dataclass
class SearchError:
    kind: SearchErrorKind
    provider: str
    message: str
    retryable: bool = False
    status_code: int | None = None
