"""四引擎并列搜索测试：URL 去重、并发容错、限流重试、防无限重试。"""

import pytest

from src.collector.rate_limiter import PlatformRateLimiter, PlatformRateLimit
from src.search import SearchBackend, SearchResult
from src.search.search_all import search_all_backends


class _MockBackend(SearchBackend):
    def __init__(self, name: str, results=None, error=None):
        self.name = name
        self._results = results or []
        self._error = error

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        if self._error:
            raise self._error
        return self._results


class _FlakyBackend(SearchBackend):
    """前 empty_times 次返回空（模拟 429/超时），之后返回一条结果。"""

    def __init__(self, name: str = "tavily", empty_times: int = 1):
        self.name = name
        self._empty_times = empty_times
        self.calls = 0

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        self.calls += 1
        if self.calls <= self._empty_times:
            return []
        return [SearchResult(title="A", snippet="s", url="https://a.com/1")]


def _fast_limiter(name: str = "tavily") -> PlatformRateLimiter:
    return PlatformRateLimiter(name, PlatformRateLimit(
        max_concurrent=2, min_interval_seconds=0.0,
        max_requests_per_minute=None,
        backoff_base_seconds=0.01, backoff_max_seconds=0.02,
    ))


@pytest.mark.asyncio
async def test_dedup_by_url_first_provider_wins():
    b1 = _MockBackend("tavily", [SearchResult(title="A", snippet="s1", url="https://a.com/1")])
    b2 = _MockBackend("duckduckgo", [
        SearchResult(title="A dup", snippet="s1", url="https://a.com/1"),  # 重复 URL
        SearchResult(title="B", snippet="s2", url="https://b.com/2"),
    ])
    out = await search_all_backends("香格里拉 广州", backends=[b1, b2])
    assert [r["url"] for r in out] == ["https://a.com/1", "https://b.com/2"]
    assert out[0]["provider"] == "tavily"
    assert out[1]["provider"] == "duckduckgo"


@pytest.mark.asyncio
async def test_single_backend_failure_does_not_block():
    b1 = _MockBackend("tavily", error=RuntimeError("boom"))
    b2 = _MockBackend("duckduckgo", [SearchResult(title="B", snippet="s2", url="https://b.com/2")])
    out = await search_all_backends("q", backends=[b1, b2])
    assert [r["url"] for r in out] == ["https://b.com/2"]


@pytest.mark.asyncio
async def test_empty_url_skipped():
    b1 = _MockBackend("tavily", [SearchResult(title="", snippet="", url="")])
    out = await search_all_backends("q", backends=[b1])
    assert out == []


@pytest.mark.asyncio
async def test_retry_on_empty_result():
    backend = _FlakyBackend(empty_times=1)
    out = await search_all_backends("q", backends=[backend], limiters={"tavily": _fast_limiter()})
    assert len(out) == 1
    assert backend.calls == 2  # 首次空 → 退避重试一次 → 成功


@pytest.mark.asyncio
async def test_no_infinite_retry_when_always_empty():
    backend = _FlakyBackend(empty_times=99)
    out = await search_all_backends("q", backends=[backend], limiters={"tavily": _fast_limiter()})
    assert out == []
    assert backend.calls == 3  # search_max_retries=2 → 最多 3 次尝试


def test_limiters_cached_across_calls():
    """限流器必须跨查询复用，RPM 滑动窗口才累积（防回归：每次新建则限流失效）。"""
    from src.config import settings
    from src.search.search_all import _get_cached_limiters, _limiter_cache

    _limiter_cache.clear()
    try:
        l1 = _get_cached_limiters(settings)
        l2 = _get_cached_limiters(settings)
        assert l1 is l2
    finally:
        _limiter_cache.clear()
