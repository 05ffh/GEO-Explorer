"""DuckDuckGo Search Adapter — low quality fallback only (P0-6)."""

import logging

from src.config import settings
from src.search.search_adapter import SearchAdapter, EnhancedSearchResult
from src.search.duckduckgo_backend import DuckDuckGoBackend

logger = logging.getLogger(__name__)


class DuckDuckGoSearchAdapter(SearchAdapter):
    """Wraps DuckDuckGoBackend. Fallback only, never primary GT evidence source."""

    name = "duckduckgo"
    is_fallback = True

    def __init__(self, backend: DuckDuckGoBackend):
        self._backend = backend

    @property
    def status(self) -> str:
        if not settings.gt_search_duckduckgo_enabled:
            return "disabled"
        return "enabled"

    async def search(self, query: str, language: str = "zh",
                     region: str = "CN", limit: int = 10) -> list[EnhancedSearchResult]:
        if not self.is_available():
            return []

        try:
            raw_results = await self._backend.search(query, num=min(limit, 10))
        except Exception:
            logger.warning("DuckDuckGo search failed: %s", query[:80], exc_info=True)
            return []

        enhanced = []
        for i, r in enumerate(raw_results):
            tier = self._classify_tier(r.url)
            # P0-6: DuckDuckGo results are capped at B tier max
            if tier in ("S", "A"):
                tier = "B"
            enhanced.append(EnhancedSearchResult(
                title=r.title, url=r.url, snippet=r.snippet,
                provider="duckduckgo", rank=i + 1,
                source_tier=tier,
                raw={"quality": r.source_quality, "fallback": True},
            ))
        return enhanced

    def _classify_tier(self, url: str, field_name: str = "") -> str:
        """Override: DuckDuckGo cannot auto-S tier (P0-6). Cap at A."""
        tier = SearchAdapter._classify_tier(url, field_name)
        if tier == "S":
            return "A"
        return tier
