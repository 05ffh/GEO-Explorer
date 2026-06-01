"""Tests for circuit breaker module (P1-5)."""
import pytest
from unittest.mock import AsyncMock, patch
from src.queue.circuit_breaker import (
    _global_key, _org_key, FAILURE_THRESHOLD, RESET_SECONDS,
)


class TestCircuitBreakerKeys:
    def test_global_key_format(self):
        key = _global_key("kimi")
        assert key == "platform_health:global:kimi"

    def test_org_key_format(self):
        key = _org_key("org-123", "deepseek")
        assert key == "platform_health:org:org-123:deepseek"

    def test_global_and_org_keys_differ(self):
        assert _global_key("kimi") != _org_key("org-1", "kimi")


class TestCircuitBreakerConstants:
    def test_failure_threshold(self):
        assert FAILURE_THRESHOLD == 5

    def test_reset_seconds(self):
        assert RESET_SECONDS == 300


class TestCircuitBreakerWithMock:
    @pytest.mark.asyncio
    async def test_check_returns_true_when_closed(self):
        with patch("src.queue.circuit_breaker._get_redis") as mock_redis:
            r = AsyncMock()
            r.hget.return_value = "closed"  # circuit state
            mock_redis.return_value = r
            result = await _check_circuit_wrapper("closed", None)
            assert result is True

    @pytest.mark.asyncio
    async def test_record_success_resets_failure_count(self):
        with patch("src.queue.circuit_breaker._get_redis") as mock_redis:
            r = AsyncMock()
            mock_redis.return_value = r
            from src.queue.circuit_breaker import record_success
            await record_success("kimi", "org-1")
            # Verify hset was called
            assert r.hset.called

    @pytest.mark.asyncio
    async def test_record_failure_increments_count(self):
        with patch("src.queue.circuit_breaker._get_redis") as mock_redis:
            r = AsyncMock()
            # Return values for: failure_count (global), circuit_state (global), failure_count (org), circuit_state (org)
            r.hget.side_effect = ["3", "closed", "3", "closed"]
            mock_redis.return_value = r
            from src.queue.circuit_breaker import record_failure
            result = await record_failure("kimi", "RateLimitError", "org-1")
            assert "circuit_changed" in result

    @pytest.mark.asyncio
    async def test_get_all_health_returns_all_platforms(self):
        with patch("src.queue.circuit_breaker._get_redis") as mock_redis:
            r = AsyncMock()
            r.hgetall.return_value = {}
            mock_redis.return_value = r
            from src.queue.circuit_breaker import get_all_health
            health = await get_all_health()
            assert "kimi" in health
            assert "deepseek" in health
            assert "doubao" in health
            assert "wenxin" in health


async def _check_circuit_wrapper(state: str, open_since=None):
    """Helper to test circuit check without full Redis dependency."""
    from datetime import datetime, timezone
    from unittest.mock import patch

    class FakeRedis:
        def __init__(self):
            self.data = {"circuit_state": state}
            if open_since:
                self.data["circuit_open_since"] = open_since

        async def hget(self, key, field):
            return self.data.get(field)

        async def hset(self, key, mapping=None, **kwargs):
            if mapping:
                self.data.update(mapping)

        async def hgetall(self, key):
            return self.data

    with patch("src.queue.circuit_breaker._get_redis") as mock_redis:
        r = FakeRedis()
        mock_redis.return_value = r

        from src.queue.circuit_breaker import check
        now = datetime.now(timezone.utc)
        result = await check("kimi")
        return result
