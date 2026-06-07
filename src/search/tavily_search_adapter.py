"""Tavily Search Adapter — primary GT search source."""

import logging

from src.config import settings
from src.search.search_adapter import SearchAdapter, EnhancedSearchResult
from src.search.tavily_backend import TavilyBackend

logger = logging.getLogger(__name__)


class TavilySearchAdapter(SearchAdapter):
    """Wraps TavilyBackend to produce normalized EnhancedSearchResult."""

    name = "tavily"

    def __init__(self, backend: TavilyBackend | None,
                 max_results: int = 10, search_depth: str = "advanced"):
        self._backend = backend
        self._max_results = max_results
        self._search_depth = search_depth

    @property
    def status(self) -> str:
        if not settings.gt_search_tavily_enabled:
            return "disabled"
        if not settings.tavily_api_key or self._backend is None:
            return "pending_config"
        return "enabled"

    async def search(self, query: str, language: str = "zh",
                     region: str = "CN", limit: int = 10) -> list[EnhancedSearchResult]:
        if not self.is_available():
            logger.warning("TavilySearchAdapter not available: status=%s", self.status)
            return []

        try:
            raw_results = await self._backend.search(
                query, num=min(limit, self._max_results),
            )
        except Exception:
            logger.warning("Tavily search failed for query: %s", query[:80], exc_info=True)
            return []

        enhanced = []
        for i, r in enumerate(raw_results):
            tier = self._classify_tier(r.url)
            enhanced.append(EnhancedSearchResult(
                title=r.title,
                url=r.url,
                snippet=r.snippet,
                provider="tavily",
                rank=i + 1,
                source_tier=tier,
                raw={"quality": r.source_quality},
            ))
        return enhanced
