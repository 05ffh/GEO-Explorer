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
    if config.google_search_api_key and config.google_search_cx:
        pass  # Google backend registration point
    return backends
