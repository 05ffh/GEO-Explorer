"""Redis-based rate limiter — shared state across processes/containers."""
import time
import hashlib
import logging
from fastapi import Request, HTTPException

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis_client):
        self.redis = redis_client

    def _key(self, prefix: str, identifier: str, window: int) -> str:
        return f"ratelimit:{prefix}:{identifier}:{window}"

    async def check(self, prefix: str, identifier: str, max_requests: int,
                    window_seconds: int) -> tuple[bool, int, int]:
        """Check rate limit. Returns (allowed, remaining, reset_seconds)."""
        import redis as redis_lib
        now = int(time.time())
        window_key = now // window_seconds
        key = self._key(prefix, identifier, window_key)

        try:
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, window_seconds * 2)
            remaining = max(0, max_requests - count)
            reset_seconds = window_seconds - (now % window_seconds)
            return count <= max_requests, remaining, reset_seconds
        except redis_lib.RedisError as e:
            logger.error(f"Rate limiter Redis error: {e}")
            return True, 0, 0  # Fail open


def get_rate_limiter():
    """Lazy init: return Redis-based rate limiter."""
    import redis as redis_lib
    from src.config import settings
    try:
        r = redis_lib.from_url(settings.redis_url, decode_responses=True)
        r.ping()
        return RateLimiter(r)
    except Exception:
        logger.warning("Redis not available, rate limiter disabled")
        return None


async def check_rate_limit(request: Request, prefix: str, identifier: str,
                           max_requests: int, window_seconds: int):
    """FastAPI middleware-compatible rate limit check. Raises 429 if exceeded."""
    from src.config import settings
    if not settings.rate_limit_enabled:
        return

    limiter = get_rate_limiter()
    if limiter is None:
        return  # Redis not available, fail open

    allowed, remaining, reset_seconds = await limiter.check(
        prefix, identifier, max_requests, window_seconds
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"error_code": "RATE_LIMITED", "message": "请求过于频繁，请稍后重试",
                    "retry_after": reset_seconds},
            headers={"Retry-After": str(reset_seconds)},
        )


def client_ip(request: Request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"
