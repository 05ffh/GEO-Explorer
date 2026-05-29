from src.search import SearchBackend, SearchResult, PlatformCapabilities

PLATFORM_CAPS = {
    "deepseek": PlatformCapabilities(supports_web_search=True, supports_citations=True),
    "kimi": PlatformCapabilities(supports_web_search=True, supports_citations=True),
    "doubao": PlatformCapabilities(supports_web_search=False, supports_citations=False),
    "wenxin": PlatformCapabilities(supports_web_search=False, supports_citations=False),
}


class AISearchBackend(SearchBackend):
    name = "ai_search"

    def __init__(self, platform_name: str, adapter):
        self.platform_name = platform_name
        self.adapter = adapter
        self.caps = PLATFORM_CAPS.get(platform_name, PlatformCapabilities())

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        if not self.caps.supports_web_search:
            return []
        try:
            response = await self.adapter.query(query, search_enabled=True)
            return [SearchResult(
                title="", snippet=response.answer_text[:500], url="",
                source_quality="medium",
            )] if response.answer_text else []
        except Exception:
            return []
