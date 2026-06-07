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
        """P0-4: Classify source tier by URL/domain, NOT by provider.

        S: gov/edu, brand official sites (determined by canonical domain patterns)
        A: tianyancha, qichacha, industry association databases
        B: major media, wikis, business databases
        C: general news, vertical media, blogs
        D: forums, self-media, low-quality aggregators
        """
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower()

        # S-tier: government, education, official
        if any(k in domain for k in (".gov.cn", ".gov", ".edu.cn", ".edu")):
            return "S"
        # S-tier: official IR/announcement URLs
        if any(k in url.lower() for k in ("/investor", "/ir", "/announcement", "/about")):
            if not any(k in domain for k in ("zhihu.com", "zhidao", "tieba", "douban")):
                return "S"

        # A-tier: authoritative third-party databases
        if any(k in domain for k in (
            "tianyancha.com", "qichacha.com", "gsxt.gov.cn",
            "sec.gov", "sec.report", "bloomberg.com",
        )):
            return "A"

        # B-tier: major media, wikis, business databases
        if any(k in domain for k in (
            "wikipedia.org", "baidu.com/baike", "36kr.com",
            "crunchbase.com", "linkedin.com",
        )):
            return "B"
        if any(k in domain for k in (
            "sina.com", "qq.com", "163.com", "sohu.com",
            "thepaper.cn", "ft.com", "wsj.com", "reuters.com",
        )):
            return "B"

        # D-tier: forums, self-media, low-quality
        if any(k in domain for k in (
            "zhihu.com", "zhidao.baidu.com", "tieba.baidu.com",
            "douban.com", "xiaohongshu.com", "weibo.com",
        )):
            return "D"
        if "blog" in domain or "forum" in domain or "bbs" in domain:
            return "D"

        # Default: C-tier
        return "C"
