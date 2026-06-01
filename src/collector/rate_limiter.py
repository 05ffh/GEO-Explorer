"""PlatformRateLimiter — per-platform concurrency + rate + cooldown control."""
import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PlatformRateLimit:
    max_concurrent: int
    min_interval_seconds: float
    max_requests_per_minute: int | None
    cooldown_on_429_seconds: int
    consecutive_429_threshold: int


class PlatformRateLimiter:
    def __init__(self, platform: str, config: PlatformRateLimit):
        self.platform = platform
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self._last_request_at = 0.0
        self._cooldown_until = 0.0
        self._rate_limit_hits = 0
        self._request_timestamps: deque[float] = deque()

    async def acquire_or_wait(self, max_wait: float) -> bool:
        """Wait for a request slot. Returns False if budget exhausted or in cooldown."""
        deadline = time.monotonic() + max_wait

        while time.monotonic() < deadline:
            now = time.monotonic()

            # Check cooldown
            if now < self._cooldown_until:
                wait = min(self._cooldown_until - now, deadline - now)
                if wait <= 0:
                    return False
                await asyncio.sleep(wait)
                continue

            # Check RPM limit
            if self.config.max_requests_per_minute:
                self._clean_timestamps(now)
                if len(self._request_timestamps) >= self.config.max_requests_per_minute:
                    oldest = self._request_timestamps[0]
                    wait = min(oldest + 60.0 - now, deadline - now)
                    if wait <= 0:
                        return False
                    await asyncio.sleep(wait)
                    continue

            # Check min interval
            elapsed = now - self._last_request_at
            if elapsed < self.config.min_interval_seconds:
                wait = min(self.config.min_interval_seconds - elapsed, deadline - now)
                if wait <= 0:
                    return False
                await asyncio.sleep(wait)
                continue

            # Try to acquire semaphore
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=deadline - now)
                self._last_request_at = time.monotonic()
                if self.config.max_requests_per_minute:
                    self._request_timestamps.append(self._last_request_at)
                return True
            except asyncio.TimeoutError:
                return False

        return False

    def release(self):
        self._semaphore.release()

    def on_rate_limit(self):
        self._rate_limit_hits += 1
        if self._rate_limit_hits >= self.config.consecutive_429_threshold:
            self._cooldown_until = time.monotonic() + self.config.cooldown_on_429_seconds
            logger.warning(
                f"[{self.platform}] Cooldown activated for {self.config.cooldown_on_429_seconds}s "
                f"after {self._rate_limit_hits} consecutive 429s"
            )

    def on_success(self):
        self._rate_limit_hits = 0

    def is_in_cooldown(self) -> bool:
        return time.monotonic() < self._cooldown_until

    def _clean_timestamps(self, now: float):
        cutoff = now - 60.0
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()


def build_rate_limiters(platforms: list[str]) -> dict[str, PlatformRateLimiter]:
    from src.config import settings
    limiters = {}
    for p in platforms:
        cfg = settings.platform_rate_limits.get(p, {})
        limiters[p] = PlatformRateLimiter(p, PlatformRateLimit(
            max_concurrent=cfg.get("max_concurrent", 2),
            min_interval_seconds=cfg.get("min_interval_seconds", 0.5),
            max_requests_per_minute=cfg.get("max_requests_per_minute"),
            cooldown_on_429_seconds=cfg.get("cooldown_on_429_seconds", 30),
            consecutive_429_threshold=cfg.get("consecutive_429_threshold", 3),
        ))
    return limiters
