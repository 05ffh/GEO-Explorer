"""Tests for DLQ module (P1-5)."""
import pytest
from src.queue.dlq import (
    get_dlq_retry_policy, get_dlq_backoff, DLQ_BACKOFF_SCHEDULE,
)


class TestDLQRetryPolicy:
    def test_rate_limit_auto(self):
        assert get_dlq_retry_policy("RateLimitError") == "auto"

    def test_connection_error_auto(self):
        assert get_dlq_retry_policy("ConnectionError") == "auto"

    def test_timeout_error_auto(self):
        assert get_dlq_retry_policy("TimeoutError") == "auto"

    def test_validation_error_never(self):
        assert get_dlq_retry_policy("ValidationError") == "never"

    def test_auth_error_never(self):
        assert get_dlq_retry_policy("AuthenticationError") == "never"

    def test_brand_not_found_never(self):
        assert get_dlq_retry_policy("BrandNotFoundError") == "never"

    def test_config_error_never(self):
        assert get_dlq_retry_policy("ConfigurationError") == "never"

    def test_unknown_error_manual(self):
        assert get_dlq_retry_policy("SomeRandomError") == "manual"


class TestDLQBackoff:
    def test_first_requeue_5min(self):
        assert get_dlq_backoff(0) == 300

    def test_second_requeue_15min(self):
        assert get_dlq_backoff(1) == 900

    def test_third_requeue_30min(self):
        assert get_dlq_backoff(2) == 1800

    def test_beyond_schedule_capped(self):
        assert get_dlq_backoff(10) == 1800  # capped at last value

    def test_schedule_length(self):
        assert len(DLQ_BACKOFF_SCHEDULE) == 3
