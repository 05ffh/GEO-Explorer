"""Doubao Search API backend — 火山引擎豆包搜索（字节系信源）。

独立于豆包大模型的联网检索 API，信源以今日头条、抖音百科等字节系内容为主。
Custom 版本针对中文内容，返回正文更完整。
"""

import asyncio
import logging

import httpx

from src.search import SearchBackend, SearchResult

logger = logging.getLogger(__name__)

DOUBAO_SEARCH_API_URL = "https://open.feedcoopapi.com/search_api/web_search"

# 字节系高权威信源
HIGH_AUTHORITY_SITES = ["gov.cn", "旅游局", "文旅局", "官网", "baike"]


class DoubaoSearchBackend(SearchBackend):
    """豆包搜索后端 — custom 版本，中文内容，字节系信源。"""

    name = "doubao_search"

    def __init__(self, api_key: str):
        if not api_key or not api_key.strip():
            raise ValueError(
                "Doubao search backend is enabled but DOUBAO_SEARCH_API_KEY is missing. "
                "Set DOUBAO_SEARCH_API_KEY in .env or disable the backend."
            )
        self.api_key = api_key

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    DOUBAO_SEARCH_API_URL,
                    json={"Query": query, "SearchType": "web", "Count": num},
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code != 200:
                    logger.warning(
                        "Doubao search returned %d for query: %s",
                        resp.status_code, query[:80],
                    )
                    return []

                data = resp.json()
                if data.get("ResponseMetadata", {}).get("Error"):
                    logger.warning(
                        "Doubao search API error: %s",
                        data["ResponseMetadata"]["Error"].get("Message", "unknown"),
                    )
                    return []

                results = []
                for r in (data.get("Result", {}).get("WebResults") or []):
                    snippet = r.get("Summary") or r.get("Snippet") or r.get("Content") or ""
                    site = r.get("SiteName", "") or ""
                    quality = "high" if any(kw in site for kw in HIGH_AUTHORITY_SITES) else "medium"
                    results.append(SearchResult(
                        title=r.get("Title", ""),
                        snippet=snippet,
                        url=r.get("Url", ""),
                        source_quality=quality,
                    ))
                return results
        except (httpx.HTTPError, asyncio.TimeoutError, ValueError, KeyError) as e:
            logger.warning(
                "Doubao search failed for query: %s", query[:80],
                extra={"error_code": "search_backend_failed", "backend": "doubao_search"},
            )
            return []
