import asyncio
import logging

from duckduckgo_search import DDGS
from src.search import SearchBackend, SearchResult

logger = logging.getLogger(__name__)

OFFICIAL_DOMAIN_MARKERS = [".gov.cn", ".gov", "tianyancha.com", "qichacha.com"]


class DuckDuckGoBackend(SearchBackend):
    name = "duckduckgo"

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        results = []
        try:
            raw_results = await asyncio.to_thread(self._sync_search, query, num)
            for r in raw_results:
                quality = self._classify_quality(r.get("href", ""))
                results.append(SearchResult(
                    title=r.get("title", ""),
                    snippet=r.get("body", ""),
                    url=r.get("href", ""),
                    source_quality=quality,
                ))
        except Exception:
            logger.warning("DuckDuckGo search failed for query: %s", query[:80], exc_info=True)
        return results

    def _sync_search(self, query: str, num: int) -> list[dict]:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=num))

    def _classify_quality(self, url: str) -> str:
        if any(kw in url for kw in OFFICIAL_DOMAIN_MARKERS):
            return "medium"
        return "low"
