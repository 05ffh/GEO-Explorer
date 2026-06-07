"""Platform rate limiting — 429 classification, Retry-After, backoff, cooldown."""

import pytest
import time
from src.collector.error_codes import CollectorErrorCode, RETRYABLE_ERRORS, is_retryable
from src.collector.rate_limiter import PlatformRateLimiter, PlatformRateLimit, RateLimitSnapshot


def make_config(**overrides):
    defaults = {
        "max_concurrent": 2, "min_interval_seconds": 0.1,
        "max_requests_per_minute": 10, "max_tokens_per_minute": None,
        "cooldown_on_429_seconds": 30, "consecutive_429_threshold": 3,
        "max_retries": 3, "retry_after_respected": True,
        "backoff_base_seconds": 10, "backoff_max_seconds": 60,
        "enabled": True, "disabled_reason": "",
    }
    defaults.update(overrides)
    return PlatformRateLimit(**defaults)


class TestErrorCodes:
    def test_429_is_platform_rate_limited(self):
        assert CollectorErrorCode.PLATFORM_RATE_LIMITED == "platform_rate_limited"
        assert is_retryable(CollectorErrorCode.PLATFORM_RATE_LIMITED)

    def test_rate_limited_is_retryable(self):
        assert CollectorErrorCode.PLATFORM_RATE_LIMITED in RETRYABLE_ERRORS

    def test_auth_failed_is_not_retryable(self):
        assert not is_retryable(CollectorErrorCode.PLATFORM_AUTH_FAILED)

    def test_legacy_rate_limit_maps_to_platform_rate_limited(self):
        assert CollectorErrorCode.RATE_LIMIT == CollectorErrorCode.PLATFORM_RATE_LIMITED


class TestRetryAfter:
    def test_parse_retry_after_seconds(self):
        limiter = PlatformRateLimiter("test", make_config())
        val = limiter.parse_retry_after({"Retry-After": "120"})
        assert val == 120

    def test_parse_retry_after_lowercase(self):
        limiter = PlatformRateLimiter("test", make_config())
        val = limiter.parse_retry_after({"retry-after": "30"})
        assert val == 30

    def test_parse_retry_after_none(self):
        limiter = PlatformRateLimiter("test", make_config())
        val = limiter.parse_retry_after(None)
        assert val == 0

    def test_parse_retry_after_missing(self):
        limiter = PlatformRateLimiter("test", make_config())
        val = limiter.parse_retry_after({"X-Custom": "value"})
        assert val == 0


class TestBackoff:
    def test_backoff_with_retry_after(self):
        limiter = PlatformRateLimiter("test", make_config())
        delay = limiter.compute_backoff(attempt=1, retry_after=60)
        # retry_after=60 + jitter up to 5s
        assert 60 <= delay <= 65

    def test_backoff_without_retry_after(self):
        limiter = PlatformRateLimiter("test", make_config())
        delay = limiter.compute_backoff(attempt=2, retry_after=0)
        # base=10 * 2^2 = 40, + 30% jitter (0-12)
        assert 40 <= delay <= 52

    def test_backoff_capped_at_max(self):
        limiter = PlatformRateLimiter("test", make_config(backoff_max_seconds=60))
        delay = limiter.compute_backoff(attempt=10, retry_after=0)
        # base=10 * 2^10 = 10240, capped at 60 + jitter
        assert delay <= 60 + 60 * 0.3


class TestCooldown:
    def test_cooldown_triggers_after_threshold(self):
        limiter = PlatformRateLimiter("test", make_config(consecutive_429_threshold=2))
        assert not limiter.is_in_cooldown
        limiter.on_rate_limit(retry_after=10)
        assert not limiter.is_in_cooldown  # 1st 429, no cooldown yet
        limiter.on_rate_limit(retry_after=10)
        assert limiter.is_in_cooldown  # 2nd 429 triggers cooldown

    def test_success_resets_consecutive_count(self):
        limiter = PlatformRateLimiter("test", make_config(consecutive_429_threshold=2))
        limiter.on_rate_limit()
        limiter.on_success()
        limiter.on_rate_limit()
        assert not limiter.is_in_cooldown  # success reset counter

    def test_429_snapshot_records_state(self):
        limiter = PlatformRateLimiter("test", make_config(
            max_requests_per_minute=60, max_tokens_per_minute=800000,
        ))
        snapshot = limiter.on_rate_limit(retry_after=45)
        assert isinstance(snapshot, RateLimitSnapshot)
        assert snapshot.current_rpm == 60
        assert snapshot.current_tpm == 800000
        assert snapshot.retry_after_seconds == 45


class TestHealthStatus:
    def test_disabled_when_not_enabled(self):
        limiter = PlatformRateLimiter("test", make_config(enabled=False))
        assert limiter.health_status() == "disabled"

    def test_rate_limited_in_cooldown(self):
        limiter = PlatformRateLimiter("test", make_config(consecutive_429_threshold=1))
        limiter.on_rate_limit()
        assert limiter.health_status() == "rate_limited"

    def test_healthy(self):
        limiter = PlatformRateLimiter("test", make_config())
        assert limiter.health_status() == "healthy"
