import logging

import httpx

from src.search import SearchBackend, SearchResult

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"

HIGH_QUALITY_DOMAINS = [".gov.cn", ".gov", "tianyancha.com", "qichacha.com"]


class TavilyBackend(SearchBackend):
    """Tavily Search API backend — AI-powered web search with content extraction."""

    name = "tavily"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        self._last_answer = ""
        self._last_answer_urls: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    TAVILY_API_URL,
                    json={
                        "query": query,
                        "search_depth": "basic",
                        "max_results": num,
                        "include_answer": True,
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Tavily API returned %d for query: %s",
                        resp.status_code, query[:80],
                    )
                    return []

                data = resp.json()
                results = []
                for r in data.get("results", []):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        snippet=r.get("content", ""),
                        url=r.get("url", ""),
                        source_quality=self._classify_quality(r.get("url", "")),
                    ))

                # P1-2: Capture Tavily AI answer as summary evidence
                self._last_answer = data.get("answer", "") or ""
                self._last_answer_urls = [r.get("url", "") for r in data.get("results", [])[:5]]

                return results
        except Exception:
            logger.warning(
                "Tavily search failed for query: %s", query[:80], exc_info=True,
            )
            return []

    def _classify_quality(self, url: str) -> str:
        if any(kw in url for kw in HIGH_QUALITY_DOMAINS):
            return "high"
        return "medium"
