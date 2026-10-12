"""四引擎并列搜索：三个系统后端（Tavily/豆包/DDG）并发 + URL 去重 + 限流。

WebSearch（主 agent）不在此函数内，由主 agent 并列补入同一去重池。
限流复用 PlatformRateLimiter（semaphore + RPM + 退避），从源头防 429/封禁。
"""
import asyncio

from src.collector.rate_limiter import PlatformRateLimiter, PlatformRateLimit
from src.config import settings
from src.search import SearchBackend, get_available_backends


_limiter_cache: dict[str, PlatformRateLimiter] = {}


def _build_limiters(config) -> dict[str, PlatformRateLimiter]:
    """按 config.search_rate_limits 为每个搜索后端建一个限流器。"""
    limiters: dict[str, PlatformRateLimiter] = {}
    for name, cfg in config.search_rate_limits.items():
        limiters[name] = PlatformRateLimiter(name, PlatformRateLimit(
            max_concurrent=cfg.get("max_concurrent", 1),
            min_interval_seconds=cfg.get("min_interval_seconds", 0.2),
            max_requests_per_minute=cfg.get("max_requests_per_minute"),
            max_tokens_per_minute=None,  # 搜索不按 token 计
            backoff_base_seconds=cfg.get("backoff_base_seconds", 5),
            backoff_max_seconds=cfg.get("backoff_max_seconds", 60),
        ))
    return limiters


def _get_cached_limiters(config) -> dict[str, PlatformRateLimiter]:
    """进程级缓存限流器：RPM 滑动窗口必须跨查询累积，否则限流失效。"""
    global _limiter_cache
    if not _limiter_cache:
        _limiter_cache = _build_limiters(config)
    return _limiter_cache


async def _search_with_limit(
    backend: SearchBackend,
    limiter: PlatformRateLimiter | None,
    query: str,
    num: int,
    max_retries: int,
) -> list:
    """节流 + 重试：acquire 占槽 → search → 空结果退避重试。

    后端失败/429/超时都返回 []，故用「空结果」作失败信号重试。
    """
    if limiter is None:
        return await backend.search(query, num=num)
    for attempt in range(max_retries + 1):
        ok = await limiter.acquire_or_wait(max_wait=30.0)
        if not ok:
            return []  # 预算耗尽，放弃本轮
        try:
            results = await backend.search(query, num=num)
        finally:
            limiter.release()
        if results:
            limiter.on_success()
            return results
        if attempt < max_retries:
            await asyncio.sleep(limiter.compute_backoff(attempt))
    return []


async def search_all_backends(
    query: str,
    backends: list[SearchBackend] | None = None,
    config=settings,
    num: int = 5,
    limiters: dict[str, PlatformRateLimiter] | None = None,
) -> list[dict]:
    """并发跑系统后端，URL 去重，返回 [{url, title, snippet, provider}]。

    backends/limiters 可注入（测试用 mock），缺省按 config 构建。
    单后端失败不阻塞其他（gather return_exceptions=True）。
    """
    if backends is None:
        backends = get_available_backends(config)
    if limiters is None:
        limiters = _get_cached_limiters(config)
    gathered = await asyncio.gather(
        *[_search_with_limit(b, limiters.get(b.name), query, num, config.search_max_retries) for b in backends],
        return_exceptions=True,
    )
    seen: set[str] = set()
    out: list[dict] = []
    for backend, results in zip(backends, gathered):
        if isinstance(results, BaseException):
            continue
        for r in results:
            url = (r.url or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            out.append({
                "url": url,
                "title": r.title or "",
                "snippet": r.snippet or "",
                "provider": backend.name,
                "published_at": getattr(r, "published_at", "") or "",
            })
    return out
