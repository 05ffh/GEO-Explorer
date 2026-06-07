from dataclasses import dataclass, field


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    source_quality: str = "low"


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
    # Google CSE removed — GCP Custom Search JSON API not yet enabled
    return backends


def get_gt_search_adapters(config) -> list:
    """Build ordered GT Search adapters: Tavily → Google CSE → DuckDuckGo.

    Returns list of SearchAdapter instances for use by GTSearchService.
    """
    from src.search.tavily_search_adapter import TavilySearchAdapter
    from src.search.tavily_backend import TavilyBackend
    from src.search.google_cse_search_adapter import GoogleCSESearchAdapter
    from src.search.google_backend import GoogleBackend
    from src.search.duckduckgo_search_adapter import DuckDuckGoSearchAdapter
    from src.search.duckduckgo_backend import DuckDuckGoBackend

    adapters = []

    # Tavily (primary)
    if config.tavily_api_key:
        backend = TavilyBackend(api_key=config.tavily_api_key)
        adapters.append(TavilySearchAdapter(backend))
    else:
        adapters.append(TavilySearchAdapter(None))

    # Google CSE (reserved)
    if config.google_search_api_key and config.google_search_cx:
        g_backend = GoogleBackend(
            api_key=config.google_search_api_key, cx=config.google_search_cx,
        )
        adapters.append(GoogleCSESearchAdapter(g_backend))
    else:
        adapters.append(GoogleCSESearchAdapter(None))

    # DuckDuckGo (fallback)
    adapters.append(DuckDuckGoSearchAdapter(DuckDuckGoBackend()))

    return adapters
