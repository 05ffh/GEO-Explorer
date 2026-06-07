import logging

import httpx

from src.search import SearchBackend, SearchResult

logger = logging.getLogger(__name__)

GOOGLE_CSE_URL = "https://www.googleapis.com/customsearch/v1"
GOOGLE_MAX_RESULTS = 10

HIGH_QUALITY_DOMAINS = [".gov.cn", ".gov", "tianyancha.com", "qichacha.com"]


class GoogleBackend(SearchBackend):
    """Google Custom Search JSON API backend."""

    name = "google"

    def __init__(self, api_key: str, cx: str):
        self.api_key = api_key
        self.cx = cx

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    GOOGLE_CSE_URL,
                    params={
                        "key": self.api_key,
                        "cx": self.cx,
                        "q": query,
                        "num": min(num, GOOGLE_MAX_RESULTS),
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Google CSE returned %d for query: %s",
                        resp.status_code, query[:80],
                    )
                    return []

                data = resp.json()
                results = []
                for item in data.get("items", []):
                    url = item.get("link", "")
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        snippet=item.get("snippet", ""),
                        url=url,
                        source_quality=self._classify_quality(url),
                    ))
                return results
        except Exception:
            logger.warning(
                "Google CSE search failed for query: %s", query[:80], exc_info=True,
            )
            return []

    def _classify_quality(self, url: str) -> str:
        if any(kw in url for kw in HIGH_QUALITY_DOMAINS):
            return "high"
        return "medium"
