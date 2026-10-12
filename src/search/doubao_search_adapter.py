"""Doubao Search Adapter — 字节系信源 GT 搜索源。"""

import asyncio
import logging

from src.config import settings
from src.search.search_adapter import SearchAdapter, EnhancedSearchResult
from src.search.doubao_search_backend import DoubaoSearchBackend

logger = logging.getLogger(__name__)


class DoubaoSearchAdapter(SearchAdapter):
    """包装 DoubaoSearchBackend，产出归一化的 EnhancedSearchResult。"""

    name = "doubao_search"

    def __init__(self, backend: DoubaoSearchBackend | None, max_results: int = 10):
        self._backend = backend
        self._max_results = max_results

    @property
    def status(self) -> str:
        if not settings.gt_search_doubao_enabled:
            return "disabled"
        if not settings.doubao_search_api_key or self._backend is None:
            return "pending_config"
        return "enabled"

    async def search(self, query: str, language: str = "zh",
                     region: str = "CN", limit: int = 10) -> list[EnhancedSearchResult]:
        if not self.is_available():
            logger.warning("DoubaoSearchAdapter not available: status=%s", self.status)
            return []

        try:
            raw_results = await self._backend.search(
                query, num=min(limit, self._max_results),
            )
        except (asyncio.TimeoutError, ValueError, RuntimeError) as e:
            logger.warning("Doubao search failed for query: %s", query[:80],
                           extra={"error_code": "search_backend_failed", "backend": "doubao_search"})
            return []

        enhanced = []
        for i, r in enumerate(raw_results):
            tier = self._classify_tier(r.url, title=r.title)
            enhanced.append(EnhancedSearchResult(
                title=r.title,
                url=r.url,
                snippet=r.snippet,
                provider="doubao_search",
                rank=i + 1,
                source_tier=tier,
                raw={"quality": r.source_quality},
            ))
        return enhanced
