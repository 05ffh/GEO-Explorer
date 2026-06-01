"""Task control — cancel via Celery revoke + cooperative signal."""
import logging
import redis.asyncio as aioredis
from src.config import settings
from src.celery_app import app

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None

CONTROL_TTL = 3600  # 1 hour


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def cancel_task(task_id: str, task_status: str, terminate: bool = False) -> dict:
    """Cancel a task. Uses revoke for queued, cooperative signal for running.

    Returns {"accepted": bool, "mechanism": str, "message": str}.
    """
    if task_status == "queued":
        # Revoke from broker — task hasn't been picked up yet
        app.control.revoke(task_id, terminate=False)
        return {"accepted": True, "mechanism": "revoke", "message": "任务已从队列中撤销"}

    if task_status in ("running", "retrying"):
        if terminate:
            app.control.revoke(task_id, terminate=True)
            return {"accepted": True, "mechanism": "terminate", "message": "任务已被强制终止"}

        # Cooperative signal — task checks at next checkpoint
        r = await _get_redis()
        await r.set(f"control:{task_id}", "cancel", ex=CONTROL_TTL)
        return {"accepted": True, "mechanism": "cooperative", "message": "取消信号已发送，任务将在下一个检查点停止"}

    return {"accepted": False, "mechanism": "none", "message": f"无法取消状态为 {task_status} 的任务"}


async def check_cancel_signal(task_id: str) -> bool:
    """Check if a cancel signal has been set. Called at task checkpoints."""
    r = await _get_redis()
    signal = await r.get(f"control:{task_id}")
    if signal and signal == "cancel":
        await r.delete(f"control:{task_id}")
        return True
    return False


async def clear_cancel_signal(task_id: str):
    r = await _get_redis()
    await r.delete(f"control:{task_id}")
