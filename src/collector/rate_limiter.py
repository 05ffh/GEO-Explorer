"""PlatformRateLimiter — per-platform concurrency + RPM + TPM + cooldown control.

Upgraded 2026-06-07:
- TPM (tokens per minute) tracking
- Retry-After header parsing
- Pre-429 request/token recording
- Exponential backoff + jitter
"""

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PlatformRateLimit:
    max_concurrent: int
    min_interval_seconds: float
    max_requests_per_minute: int | None
    max_tokens_per_minute: int | None = None
    cooldown_on_429_seconds: int = 300
    consecutive_429_threshold: int = 3
    max_retries: int = 2
    retry_after_respected: bool = True
    backoff_base_seconds: int = 30
    backoff_max_seconds: int = 900
    enabled: bool = True
    disabled_reason: str = ""


@dataclass
class RateLimitSnapshot:
    """Recorded when a 429 occurs — captures the 60s window before the event."""
    requests_last_60s: int = 0
    tokens_last_60s: int = 0
    current_rpm: int = 0
    current_tpm: int = 0
    consecutive_429s: int = 0
    retry_after_seconds: int = 0
    recorded_at: float = 0.0


class PlatformRateLimiter:
    def __init__(self, platform: str, config: PlatformRateLimit):
        self.platform = platform
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrent if config.enabled else 0)
        self._last_request_at = 0.0
        self._cooldown_until = 0.0
        self._rate_limit_hits = 0
        self._request_timestamps: deque[float] = deque()
        self._token_timestamps: deque[tuple[float, int]] = deque()  # (timestamp, token_count)
        self._last_429_snapshot: RateLimitSnapshot | None = None

        # Stats
        self.total_requests = 0
        self.total_429s = 0
        self.total_success = 0
        self._recent_latencies: deque[float] = deque(maxlen=100)

    @property
    def enabled(self) -> bool:
        return self.config.enabled and self.config.max_concurrent > 0

    @property
    def is_in_cooldown(self) -> bool:
        return time.monotonic() < self._cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        return max(0.0, self._cooldown_until - time.monotonic())

    @property
    def current_rpm(self) -> int:
        self._clean_timestamps(time.monotonic())
        return len(self._request_timestamps)

    @property
    def current_tpm(self) -> int:
        self._clean_token_timestamps(time.monotonic())
        return sum(t for _, t in self._request_timestamps) if not self._token_timestamps else sum(
            t for _, t in self._token_timestamps)

    @property
    def last_429_snapshot(self) -> RateLimitSnapshot | None:
        return self._last_429_snapshot

    def parse_retry_after(self, headers: dict | None) -> int:
        """Parse Retry-After header. Returns seconds to wait, or 0 if not present."""
        if not headers:
            return 0
        for key in ("retry-after", "Retry-After", "Retry-after"):
            val = headers.get(key)
            if val is None:
                continue
            try:
                return int(val)
            except ValueError:
                pass
            try:
                import email.utils
                retry_time = email.utils.parsedate_to_datetime(val)
                return max(0, int((retry_time.timestamp() - time.time())))
            except Exception:
                pass
        return 0

    def compute_backoff(self, attempt: int, retry_after: int = 0) -> float:
        """Compute backoff with jitter. Respects Retry-After if provided."""
        if retry_after > 0 and self.config.retry_after_respected:
            # Add small jitter to Retry-After to avoid thundering herd
            jitter = random.uniform(0, min(5, retry_after * 0.1))
            return retry_after + jitter
        base = self.config.backoff_base_seconds
        max_backoff = self.config.backoff_max_seconds
        delay = min(base * (2 ** attempt), max_backoff)
        jitter = random.uniform(0, delay * 0.3)
        return delay + jitter

    async def acquire_or_wait(self, max_wait: float, estimated_tokens: int = 500) -> bool:
        """Wait for a request slot + rate budget. Returns False if budget exhausted."""
        if not self.enabled:
            return False

        deadline = time.monotonic() + max_wait

        while time.monotonic() < deadline:
            now = time.monotonic()

            # Check cooldown
            if now < self._cooldown_until:
                wait = min(self._cooldown_until - now, deadline - now)
                if wait <= 0:
                    return False
                await asyncio.sleep(min(wait, 5.0))
                continue

            # Check RPM limit
            if self.config.max_requests_per_minute:
                self._clean_timestamps(now)
                if len(self._request_timestamps) >= self.config.max_requests_per_minute:
                    oldest = self._request_timestamps[0]
                    wait = min(oldest + 60.0 - now, deadline - now)
                    if wait <= 0:
                        return False
                    await asyncio.sleep(min(wait, 5.0))
                    continue

            # Check TPM limit
            if self.config.max_tokens_per_minute:
                self._clean_token_timestamps(now)
                current_tokens = sum(t for _, t in self._token_timestamps)
                if current_tokens + estimated_tokens > self.config.max_tokens_per_minute:
                    oldest_ts, _ = self._token_timestamps[0]
                    wait = min(oldest_ts + 60.0 - now, deadline - now)
                    if wait <= 0:
                        return False
                    await asyncio.sleep(min(wait, 5.0))
                    continue

            # Check min interval
            elapsed = now - self._last_request_at
            if elapsed < self.config.min_interval_seconds:
                wait = min(self.config.min_interval_seconds - elapsed, deadline - now)
                if wait <= 0:
                    return False
                await asyncio.sleep(min(wait, 1.0))
                continue

            # Try to acquire semaphore
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=deadline - now)
                self._last_request_at = time.monotonic()
                self._request_timestamps.append(self._last_request_at)
                if self.config.max_tokens_per_minute:
                    self._token_timestamps.append((self._last_request_at, estimated_tokens))
                self.total_requests += 1
                return True
            except asyncio.TimeoutError:
                return False

        return False

    def release(self) -> None:
        self._semaphore.release()

    def record_tokens(self, token_count: int) -> None:
        """Record actual token usage after a successful response."""
        if self.config.max_tokens_per_minute and self._last_request_at:
            # Update last timestamp entry with actual tokens
            if self._token_timestamps:
                self._token_timestamps[-1] = (self._token_timestamps[-1][0], token_count)

    def on_rate_limit(self, retry_after: int = 0, response_headers: dict | None = None) -> RateLimitSnapshot:
        """Called when a 429 is received. Records the state and may trigger cooldown."""
        self._rate_limit_hits += 1
        self.total_429s += 1

        now = time.monotonic()
        self._clean_timestamps(now)

        ra = retry_after if retry_after > 0 else self.parse_retry_after(response_headers)

        snapshot = RateLimitSnapshot(
            requests_last_60s=len(self._request_timestamps),
            tokens_last_60s=sum(t for _, t in self._token_timestamps) if self.config.max_tokens_per_minute else 0,
            current_rpm=self.config.max_requests_per_minute or 0,
            current_tpm=self.config.max_tokens_per_minute or 0,
            consecutive_429s=self._rate_limit_hits,
            retry_after_seconds=ra,
            recorded_at=now,
        )
        self._last_429_snapshot = snapshot

        if self._rate_limit_hits >= self.config.consecutive_429_threshold:
            cooldown = max(self.config.cooldown_on_429_seconds, ra)
            self._cooldown_until = now + cooldown
            logger.warning(
                f"[{self.platform}] Cooldown {cooldown}s after {self._rate_limit_hits} consecutive 429s "
                f"(RPM: {snapshot.requests_last_60s}/{snapshot.current_rpm}, "
                f"Retry-After: {ra}s)"
            )

        return snapshot

    def on_success(self) -> None:
        self._rate_limit_hits = 0
        self.total_success += 1

    def on_failure(self, error_code: str | None) -> None:
        """Record failure for health tracking."""
        pass

    def record_latency(self, latency_ms: int) -> None:
        self._recent_latencies.append(latency_ms)

    @property
    def avg_latency_ms(self) -> float:
        if not self._recent_latencies:
            return 0.0
        return sum(self._recent_latencies) / len(self._recent_latencies)

    def health_status(self) -> str:
        """Returns: healthy, degraded, rate_limited, disabled."""
        if not self.enabled:
            return "disabled"
        if self.is_in_cooldown:
            return "rate_limited"
        if self.total_requests > 0:
            error_rate = self.total_429s / self.total_requests
            if error_rate > 0.2:
                return "degraded"
        return "healthy"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _clean_timestamps(self, now: float) -> None:
        cutoff = now - 60.0
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()

    def _clean_token_timestamps(self, now: float) -> None:
        cutoff = now - 60.0
        while self._token_timestamps and self._token_timestamps[0][0] < cutoff:
            self._token_timestamps.popleft()


# ── Factory ──────────────────────────────────────────────────────────────────

def build_rate_limiters(platforms: list[str]) -> dict[str, PlatformRateLimiter]:
    from src.config import settings
    limiters = {}
    for p in platforms:
        cfg = settings.platform_rate_limits.get(p, {})
        limiters[p] = PlatformRateLimiter(p, PlatformRateLimit(
            max_concurrent=cfg.get("max_concurrent", 0),
            min_interval_seconds=cfg.get("min_interval_seconds", 0.5),
            max_requests_per_minute=cfg.get("max_requests_per_minute"),
            max_tokens_per_minute=cfg.get("max_tokens_per_minute"),
            cooldown_on_429_seconds=cfg.get("cooldown_on_429_seconds", 300),
            consecutive_429_threshold=cfg.get("consecutive_429_threshold", 3),
            max_retries=cfg.get("max_retries", 2),
            retry_after_respected=cfg.get("retry_after_respected", True),
            backoff_base_seconds=cfg.get("backoff_base_seconds", 30),
            backoff_max_seconds=cfg.get("backoff_max_seconds", 900),
            enabled=cfg.get("enabled", True),
            disabled_reason=cfg.get("disabled_reason", ""),
        ))
    return limiters
