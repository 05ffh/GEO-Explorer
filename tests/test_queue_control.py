"""Tests for control module (P1-5)."""
import pytest
from unittest.mock import AsyncMock, patch


class TestControlCancel:
    @pytest.mark.asyncio
    async def test_cancel_queued_uses_revoke(self):
        with patch("src.queue.control.app.control.revoke") as mock_revoke:
            from src.queue.control import cancel_task
            result = await cancel_task("task-123", "queued")
            assert result["accepted"] is True
            assert result["mechanism"] == "revoke"
            mock_revoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_running_uses_cooperative_signal(self):
        with patch("src.queue.control._get_redis") as mock_redis:
            r = AsyncMock()
            mock_redis.return_value = r
            from src.queue.control import cancel_task
            result = await cancel_task("task-456", "running")
            assert result["accepted"] is True
            assert result["mechanism"] == "cooperative"

    @pytest.mark.asyncio
    async def test_cancel_retrying_uses_cooperative_signal(self):
        with patch("src.queue.control._get_redis") as mock_redis:
            r = AsyncMock()
            mock_redis.return_value = r
            from src.queue.control import cancel_task
            result = await cancel_task("task-789", "retrying")
            assert result["accepted"] is True
            assert result["mechanism"] == "cooperative"

    @pytest.mark.asyncio
    async def test_cancel_completed_rejected(self):
        from src.queue.control import cancel_task
        result = await cancel_task("task-completed", "completed")
        assert result["accepted"] is False

    @pytest.mark.asyncio
    async def test_cancel_cancelled_rejected(self):
        from src.queue.control import cancel_task
        result = await cancel_task("task-cancelled", "cancelled")
        assert result["accepted"] is False

    @pytest.mark.asyncio
    async def test_cancel_dead_lettered_rejected(self):
        from src.queue.control import cancel_task
        result = await cancel_task("task-dlq", "dead_lettered")
        assert result["accepted"] is False

    @pytest.mark.asyncio
    async def test_terminate_uses_revoke_with_terminate(self):
        with patch("src.queue.control.app.control.revoke") as mock_revoke:
            from src.queue.control import cancel_task
            result = await cancel_task("task-running", "running", terminate=True)
            assert result["accepted"] is True
            assert result["mechanism"] == "terminate"
            mock_revoke.assert_called_once_with("task-running", terminate=True)

    @pytest.mark.asyncio
    async def test_check_cancel_signal_true(self):
        with patch("src.queue.control._get_redis") as mock_redis:
            r = AsyncMock()
            r.get.return_value = "cancel"
            mock_redis.return_value = r
            from src.queue.control import check_cancel_signal
            result = await check_cancel_signal("task-1")
            assert result is True

    @pytest.mark.asyncio
    async def test_check_cancel_signal_false(self):
        with patch("src.queue.control._get_redis") as mock_redis:
            r = AsyncMock()
            r.get.return_value = None
            mock_redis.return_value = r
            from src.queue.control import check_cancel_signal
            result = await check_cancel_signal("task-2")
            assert result is False
