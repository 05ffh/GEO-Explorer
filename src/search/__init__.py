from dataclasses import dataclass, field


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    source_quality: str = "low"
    published_at: str = ""   # 发布时间（时效验证；Tavily 返回 published_date，其他引擎有则填，无则空）


class SearchBackend:
    name: str = ""

    async def search(self, query: str, num: int = 5) -> list[SearchResult]:
        raise NotImplementedError


@dataclass
class PlatformCapabilities:
    supports_web_search: bool = False
    supports_citations: bool = False
    citation_format: str = ""


def get_available_backends(config) -> list[SearchBackend]:
    from src.search.duckduckgo_backend import DuckDuckGoBackend
    from src.search.tavily_backend import TavilyBackend
    backends = [DuckDuckGoBackend()]
    if config.tavily_api_key:
        backends.append(TavilyBackend(api_key=config.tavily_api_key))
    if config.doubao_search_api_key:
        from src.search.doubao_search_backend import DoubaoSearchBackend
        backends.append(DoubaoSearchBackend(api_key=config.doubao_search_api_key))
    # Google CSE removed — GCP Custom Search JSON API not yet enabled
    return backends


def get_gt_search_adapters(config) -> list:
    """Build ordered GT Search adapters: Tavily → DuckDuckGo → Doubao.

    Returns list of SearchAdapter instances for use by GTSearchService.
    """
    from src.search.tavily_search_adapter import TavilySearchAdapter
    from src.search.tavily_backend import TavilyBackend
    from src.search.duckduckgo_search_adapter import DuckDuckGoSearchAdapter
    from src.search.duckduckgo_backend import DuckDuckGoBackend

    adapters = []

    # Tavily (primary)
    if config.tavily_api_key:
        backend = TavilyBackend(api_key=config.tavily_api_key)
        adapters.append(TavilySearchAdapter(backend))
    else:
        adapters.append(TavilySearchAdapter(None))

    # DuckDuckGo (fallback)
    adapters.append(DuckDuckGoSearchAdapter(DuckDuckGoBackend()))

    # Doubao Search (字节系信源)
    if config.doubao_search_api_key:
        from src.search.doubao_search_adapter import DoubaoSearchAdapter
        from src.search.doubao_search_backend import DoubaoSearchBackend
        adapters.append(DoubaoSearchAdapter(
            DoubaoSearchBackend(api_key=config.doubao_search_api_key)
        ))
    else:
        from src.search.doubao_search_adapter import DoubaoSearchAdapter
        adapters.append(DoubaoSearchAdapter(None))

    return adapters
