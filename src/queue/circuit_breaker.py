"""Circuit breaker — Redis-based, two-level (global + org)."""
import logging
from datetime import datetime, timezone
import redis.asyncio as aioredis
from src.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None

CIRCUIT_STATES = ("closed", "open", "half_open")
FAILURE_THRESHOLD = settings.circuit_breaker_failure_threshold
RESET_SECONDS = settings.circuit_breaker_reset_seconds


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def _global_key(platform: str) -> str:
    return f"platform_health:global:{platform}"


def _org_key(org_id: str, platform: str) -> str:
    return f"platform_health:org:{org_id}:{platform}"


async def record_success(platform: str, org_id: str | None = None):
    """Record a successful platform call — resets circuit to closed."""
    r = await _get_redis()
    now = datetime.now(timezone.utc).isoformat()

    # Global
    await r.hset(_global_key(platform), mapping={
        "failure_count": "0",
        "circuit_state": "closed",
        "last_success": now,
    })

    # Org-level
    if org_id:
        await r.hset(_org_key(org_id, platform), mapping={
            "failure_count": "0",
            "circuit_state": "closed",
            "last_success": now,
        })


async def record_failure(platform: str, error_type: str,
                         org_id: str | None = None) -> dict:
    """Record a platform call failure. May trigger circuit breaker.

    Returns {"circuit_changed": bool, "org_circuit": bool, "global_circuit": bool}.
    """
    r = await _get_redis()
    now = datetime.now(timezone.utc).isoformat()
    result = {"circuit_changed": False, "org_circuit": False, "global_circuit": False}

    # Decide scope
    is_global_error = error_type in ("RateLimitError", "ConnectionError", "TimeoutError")
    is_org_error = error_type in ("AuthenticationError",)

    if is_org_error and org_id:
        changed = await _increment_failure(r, _org_key(org_id, platform), now)
        result["circuit_changed"] = changed
        result["org_circuit"] = changed

    if is_global_error:
        changed = await _increment_failure(r, _global_key(platform), now)
        result["circuit_changed"] = result["circuit_changed"] or changed
        result["global_circuit"] = changed

    # Also increment org-level for global errors
    if is_global_error and org_id:
        await _increment_failure(r, _org_key(org_id, platform), now)

    return result


async def _increment_failure(r, key: str, now: str) -> bool:
    """Increment failure count. Return True if circuit just opened."""
    current = await r.hget(key, "failure_count")
    count = int(current or 0) + 1
    circuit_state = await r.hget(key, "circuit_state") or "closed"

    await r.hset(key, mapping={
        "failure_count": str(count),
        "last_failure": now,
    })

    if count >= FAILURE_THRESHOLD and circuit_state == "closed":
        await r.hset(key, mapping={
            "circuit_state": "open",
            "circuit_open_since": now,
        })
        logger.warning(f"Circuit OPEN: {key} after {count} failures")
        return True
    return False


async def check(platform: str, org_id: str | None = None) -> bool:
    """Check if a platform call should be allowed. Returns True = proceed."""
    r = await _get_redis()
    now = datetime.now(timezone.utc)

    # Check global first
    global_state = await _check_circuit(r, _global_key(platform), now)
    if not global_state:
        logger.info(f"Global circuit OPEN for {platform}, blocked")
        return False

    # Check org-level
    if org_id:
        org_state = await _check_circuit(r, _org_key(org_id, platform), now)
        if not org_state:
            logger.info(f"Org circuit OPEN for {org_id}/{platform}, blocked")
            return False

    return True


async def _check_circuit(r, key: str, now: datetime) -> bool:
    """Check a single circuit. Transitions half_open → closed if probe succeeds."""
    state = await r.hget(key, "circuit_state") or "closed"

    if state == "closed":
        return True

    if state == "open":
        open_since_str = await r.hget(key, "circuit_open_since")
        if open_since_str:
            open_since = datetime.fromisoformat(open_since_str)
            elapsed = (now - open_since).total_seconds()
            if elapsed >= RESET_SECONDS:
                # Transition to half-open
                await r.hset(key, mapping={
                    "circuit_state": "half_open",
                    "failure_count": str(FAILURE_THRESHOLD),  # keep near threshold
                })
                logger.info(f"Circuit HALF_OPEN: {key}")
                return True  # allow the probe
        return False  # still open, block

    if state == "half_open":
        return True  # allow probe

    return True


async def get_health(platform: str, org_id: str | None = None) -> dict:
    """Get platform health status for dashboard."""
    r = await _get_redis()
    health = {}

    global_data = await r.hgetall(_global_key(platform))
    if global_data:
        health["global"] = dict(global_data)

    if org_id:
        org_data = await r.hgetall(_org_key(org_id, platform))
        if org_data:
            health["org"] = dict(org_data)

    return health


async def get_all_health() -> dict:
    """Get health for all known platforms."""
    platforms = ["kimi", "deepseek", "doubao", "wenxin"]
    result = {}
    for p in platforms:
        health = await get_health(p)
        # Determine effective state
        global_state = health.get("global", {}).get("circuit_state", "closed")
        result[p] = {"circuit_state": global_state}
    return result
