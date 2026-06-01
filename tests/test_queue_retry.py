"""Tests for manual retry strategy (P1-5)."""
import pytest
from src.queue.retry import classify_error, get_retry_delay, RETRYABLE_ERRORS, NON_RETRYABLE_ERRORS


class RateLimitError(Exception): pass
class ConnectionError(Exception): pass
class TimeoutError(Exception): pass
class ValidationError(Exception): pass
class BrandNotFoundError(Exception): pass
class AuthenticationError(Exception): pass
class UnknownError(Exception): pass


class TestClassifyError:
    def test_retryable_rate_limit(self):
        etype, policy = classify_error(RateLimitError())
        assert etype == "RateLimitError"
        assert policy == "retry"

    def test_retryable_connection(self):
        etype, policy = classify_error(ConnectionError())
        assert policy == "retry"

    def test_retryable_timeout(self):
        etype, policy = classify_error(TimeoutError())
        assert policy == "retry"

    def test_non_retryable_validation(self):
        etype, policy = classify_error(ValidationError())
        assert policy == "dlq_never"

    def test_non_retryable_brand_not_found(self):
        _, policy = classify_error(BrandNotFoundError())
        assert policy == "dlq_never"

    def test_non_retryable_auth(self):
        _, policy = classify_error(AuthenticationError())
        assert policy == "dlq_never"

    def test_unknown_error_defaults_to_manual_dlq(self):
        _, policy = classify_error(UnknownError())
        assert policy == "dlq_manual"

    def test_custom_exception_maps_to_dlq_manual(self):
        class CustomBizError(Exception): pass
        _, policy = classify_error(CustomBizError())
        assert policy == "dlq_manual"

    def test_all_retryable_errors_present(self):
        assert "RateLimitError" in RETRYABLE_ERRORS
        assert "ConnectionError" in RETRYABLE_ERRORS
        assert "TimeoutError" in RETRYABLE_ERRORS

    def test_all_non_retryable_errors_present(self):
        assert "ValidationError" in NON_RETRYABLE_ERRORS
        assert "AuthenticationError" in NON_RETRYABLE_ERRORS


class TestRetryDelay:
    def test_first_retry_delay_around_60(self):
        delay = get_retry_delay(0)
        assert 30 <= delay <= 90  # 60s ± 50% jitter

    def test_second_retry_delay_around_120(self):
        delay = get_retry_delay(1)
        assert 60 <= delay <= 180

    def test_third_retry_delay_around_240(self):
        delay = get_retry_delay(2)
        assert 120 <= delay <= 360

    def test_delay_capped_at_3600(self):
        delay = get_retry_delay(20)
        assert delay <= 3600

    def test_delay_minimum_10(self):
        # With jitter and small numbers, still at least 10
        delays = [get_retry_delay(0) for _ in range(100)]
        assert all(d >= 10 for d in delays)
