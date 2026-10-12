"""DuckDuckGo search backend — 爬 Lite 端点（无需 API Key）。

duckduckgo_search 库已废弃且返回错误结果，改用 httpx 直接请求
lite.duckduckgo.com/lite/ 并解析 HTML。
"""

import asyncio
import logging
import re

import httpx

from src.search import SearchBackend, SearchResult

logger = logging.getLogger(__name__)

LITE_URL = "https://lite.duckduckgo.com/lite/"
OFFICIAL_DOMAIN_MARKERS = [".gov.cn", ".gov", "tianyancha.com", "qichacha.com"]


class DuckDuckGoBackend(SearchBackend):
    name = "duckduckgo"

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    LITE_URL,
                    data={"q": query},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code != 200:
                    logger.warning("DuckDuckGo Lite returned %d", resp.status_code)
                    return []
                return self._parse(resp.text, num)
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            logger.warning(
                "DuckDuckGo search failed for query: %s", query[:80],
                extra={"error_code": "search_backend_failed", "backend": "duckduckgo"},
            )
            return []

    def _parse(self, html: str, num: int) -> list[SearchResult]:
        results = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
            m = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', row, re.DOTALL)
            if not m:
                continue
            url = m.group(1)
            if "duckduckgo.com" in url or url.startswith("//"):
                continue
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            snip = re.search(r"result-snippet[^>]*>(.*?)<", row, re.DOTALL)
            snippet = re.sub(r"<[^>]+>", "", snip.group(1)).strip() if snip else ""
            if not title and not url:
                continue
            results.append(SearchResult(
                title=title,
                snippet=snippet,
                url=url,
                source_quality=self._classify_quality(url),
            ))
            if len(results) >= num:
                break
        return results

    def _classify_quality(self, url: str) -> str:
        if any(kw in url for kw in OFFICIAL_DOMAIN_MARKERS):
            return "medium"
        return "low"
