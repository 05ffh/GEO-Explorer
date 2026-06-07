"""Google CSE Search Adapter — reserved, currently disabled.

4-gate check:
  1. gt_search_google_cse_enabled flag
  2. GOOGLE_SEARCH_API_KEY present
  3. GOOGLE_SEARCH_CX present
  4. GCP Custom Search JSON API enabled (lazy-checked on first call)
"""

import logging

from src.config import settings
from src.search.search_adapter import SearchAdapter, EnhancedSearchResult
from src.search.google_backend import GoogleBackend

logger = logging.getLogger(__name__)


class GoogleCSESearchAdapter(SearchAdapter):
    """Wraps GoogleBackend. Currently reserved/disabled."""

    name = "google_cse"

    def __init__(self, backend: GoogleBackend | None):
        self._backend = backend

    @property
    def status(self) -> str:
        if not settings.gt_search_google_cse_enabled:
            return "disabled"
        if not settings.google_search_api_key:
            return "pending_config"
        if not settings.google_search_cx:
            return "pending_config"
        if self._backend is None:
            return "pending_config"
        return "enabled"

    async def search(self, query: str, language: str = "zh",
                     region: str = "CN", limit: int = 10) -> list[EnhancedSearchResult]:
        if not self.is_available():
            return []

        try:
            raw_results = await self._backend.search(query, num=min(limit, 10))
        except Exception:
            logger.warning("Google CSE search failed: %s", query[:80], exc_info=True)
            return []

        enhanced = []
        for i, r in enumerate(raw_results):
            enhanced.append(EnhancedSearchResult(
                title=r.title, url=r.url, snippet=r.snippet,
                provider="google_cse", rank=i + 1,
                source_tier=self._classify_tier(r.url),
                raw={"quality": r.source_quality},
            ))
        return enhanced
