"""Public source tier classification — shared by all adapters and gt_collector.

P0-6: Extracted from SearchAdapter._classify_tier() into a standalone function
so that all search backends and the GT collector can use consistent tier logic
without depending on adapter internals.
"""

from urllib.parse import urlparse

# S-tier keywords: government, education, official IR/announcement pages
S_TIER_DOMAIN_KEYWORDS = (".gov.cn", ".gov", ".edu.cn", ".edu")
S_TIER_PATH_KEYWORDS = ("/investor", "/ir", "/announcement", "/about")

# A-tier keywords: authoritative third-party databases
A_TIER_DOMAIN_KEYWORDS = (
    "tianyancha.com", "qichacha.com", "gsxt.gov.cn",
    "sec.gov", "sec.report", "bloomberg.com",
)

# B-tier keywords: major media, wikis, business databases
B_TIER_DOMAIN_KEYWORDS = (
    "wikipedia.org", "36kr.com", "crunchbase.com", "linkedin.com",
    "sina.com", "qq.com", "163.com", "sohu.com",
    "thepaper.cn", "ft.com", "wsj.com", "reuters.com",
)

# D-tier keywords: forums, self-media, low-quality aggregators
D_TIER_DOMAIN_KEYWORDS = (
    "zhihu.com", "zhidao.baidu.com", "tieba.baidu.com",
    "douban.com", "xiaohongshu.com", "weibo.com",
)

# IR/announcement path keywords that would otherwise be B/C/D
S_TIER_DOMAIN_EXCLUDE = ("zhihu.com", "zhidao", "tieba", "douban")


def classify_source_tier(url: str, title: str | None = None,
                         field_name: str | None = None) -> str:
    """Classify source tier (S/A/B/C/D) based on URL domain and path.

    P0-6: This is a PUBLIC function usable by all adapters and the GT collector.
    Tier is determined by source_url/domain, NOT by provider.

    Returns: "S", "A", "B", "C", or "D"
    """
    if not url:
        return "C"

    domain = urlparse(url).netloc.lower()
    if not domain:
        domain = urlparse(url).path.lower().split("/")[0]

    # S-tier: government, education
    if any(k in domain for k in S_TIER_DOMAIN_KEYWORDS):
        return "S"

    # S-tier: official IR/announcement URLs (exclude forums)
    if any(k in url.lower() for k in S_TIER_PATH_KEYWORDS):
        if not any(k in domain for k in S_TIER_DOMAIN_EXCLUDE):
            return "S"

    # A-tier: authoritative third-party databases
    if any(k in domain for k in A_TIER_DOMAIN_KEYWORDS):
        return "A"

    # Boost via title context
    if title and any(k in title.lower() for k in
                     ("investor relations", "annual report", "about us",
                      "公司简介", "关于我们", "投资者关系")):
        if not any(k in domain for k in S_TIER_DOMAIN_EXCLUDE):
            return "A"

    # B-tier: major media, wikis, business databases
    if any(k in domain for k in ("wikipedia.org", "baike.baidu.com")):
        return "B"
    if any(k in domain for k in B_TIER_DOMAIN_KEYWORDS):
        return "B"

    # D-tier: forums, self-media, low-quality
    if any(k in domain for k in D_TIER_DOMAIN_KEYWORDS):
        return "D"
    if any(k in domain for k in ("blog.", "forum.", "bbs.")):
        return "D"

    return "C"
