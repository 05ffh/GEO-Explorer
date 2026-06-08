"""SearchAdapter base class and EnhancedSearchResult for the GT Search pipeline.

This is a NEW layer wrapping existing SearchBackend instances.
The old SearchResult in src/search/__init__.py remains unchanged.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class EnhancedSearchResult:
    """Normalized search result for GT Search pipeline (NOT the old SearchResult).

    P0-1: This is the OUTPUT of a SearchAdapter. It must be converted to
    GroundTruthEvidence before it can contribute to a GTCandidate.
    """
    title: str
    url: str
    snippet: str
    provider: str          # "tavily", "google_cse", "duckduckgo"
    rank: int              # 1-based position in provider results
    source_tier: str = "C"  # S/A/B/C/D — determined by source_url, not provider
    published_at: str | None = None
    raw: dict = field(default_factory=dict)


class SearchAdapter(ABC):
    """Abstract base for search provider adapters.

    Wraps an existing SearchBackend to produce normalized EnhancedSearchResult.
    """

    name: str = ""

    @property
    @abstractmethod
    def status(self) -> str:
        """Returns 'enabled', 'disabled', or 'pending_config'."""
        ...

    def is_available(self) -> bool:
        """True when all config conditions are met and the adapter can be called."""
        return self.status == "enabled"

    @abstractmethod
    async def search(
        self, query: str,
        language: str = "zh", region: str = "CN", limit: int = 10,
    ) -> list[EnhancedSearchResult]:
        """Execute a search and return normalized results. Never raises on failure."""
        ...

    @staticmethod
    def _classify_tier(url: str, field_name: str = "") -> str:
        """Classify source tier by URL/domain. Delegates to public function (P0-6)."""
        from src.search.source_tier import classify_source_tier
        return classify_source_tier(url)
