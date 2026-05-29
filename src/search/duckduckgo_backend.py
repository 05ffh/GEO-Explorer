from duckduckgo_search import DDGS
from src.search import SearchBackend, SearchResult


class DuckDuckGoBackend(SearchBackend):
    name = "duckduckgo"

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=num):
                    quality = self._classify_quality(r.get("href", ""), r.get("body", ""))
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        snippet=r.get("body", ""),
                        url=r.get("href", ""),
                        source_quality=quality,
                    ))
        except Exception:
            pass
        return results

    def _classify_quality(self, url: str, snippet: str) -> str:
        if any(kw in url for kw in [".gov.cn", ".gov", "tianyancha.com", "qichacha.com"]):
            return "medium"
        return "low"
