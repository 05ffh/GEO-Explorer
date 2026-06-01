"""Idempotency guard — Redis-based dedup with sha256 key."""
import hashlib
import logging
from datetime import datetime, timezone
import redis.asyncio as aioredis
from src.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def build_idempotency_key(*, org_id: str, task_name: str, operation_type: str,
                           payload_hash: str, time_bucket: str) -> str:
    """Construct idempotency key: idem:{org_id}:{task_name}:{op}:{hash}:{bucket}"""
    short_task = task_name.rsplit(".", 1)[-1] if "." in task_name else task_name
    return f"idem:{org_id}:{short_task}:{operation_type}:{payload_hash}:{time_bucket}"


def build_payload_hash(args: list, kwargs: dict) -> str:
    raw = str(args) + str(sorted(kwargs.items()))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_time_bucket() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H")


async def try_acquire(key: str, ttl: int = 3600) -> bool:
    """Try to set the idempotency key. Returns True if acquired (new)."""
    r = await _get_redis()
    acquired = await r.set(key, "1", nx=True, ex=ttl)
    return bool(acquired)


async def release(key: str):
    r = await _get_redis()
    await r.delete(key)


async def force_release(key: str) -> bool:
    """Force-delete an idempotency key. Returns True if key existed."""
    r = await _get_redis()
    deleted = await r.delete(key)
    return bool(deleted)
