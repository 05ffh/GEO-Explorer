"""酒旅信源 tier 判定（spec 6.1）：URL 域名 → T0-T4。

替代旧 src/search/source_tier.py 的 S/A/B/C/D 企业信源分级。
事实信源方向：官方(T0) > OTA(T1) > 点评(T2) > UGC(T3)。
"""
from urllib.parse import urlparse

from src.industry_knowledge.loader import get_knowledge_loader

# T0: 政府/文旅局（品牌官网的精确判定需品牌名，后续用 title 信号升级）
GOV_DOMAINS = (".gov.cn", ".gov")

# T1: OTA
OTA_DOMAINS = (
    "ctrip.com", "trip.com", "fliggy.com", "qunar.com", "ly.com",
    "meituan.com", "elong.com", "agoda.com", "agoda.cn", "booking.com",
    "wingontravel.com", "hotelscombined.com",
)

# T2: 点评/垂直媒体
REVIEW_DOMAINS = (
    "dianping.com", "mafengwo.cn", "qyer.com",
    "meadin.com", "traveldaily.cn",
)

# T3: UGC/百科/其他
UGC_DOMAINS = (
    "xiaohongshu.com", "douyin.com", "baike.baidu.com",
    "zhihu.com", "weibo.com", "flyert.com.cn", "bilibili.com",
)


def classify_source_tier(url: str, brand_zh: str | None = None) -> str:
    """URL 域名 → 酒旅信源 tier（T0-T4）。

    政府/文旅局 → T0；品牌官网（域名含品牌英文名，查 brand_domains）→ T0；
    OTA → T1；点评/垂直媒体 → T2；UGC/百科 → T3；未知域名 → T3。
    brand_zh 提供时才能判定品牌官网；映射表外的品牌由主 agent 辅助判定。
    """
    if not url:
        return "T3"
    domain = urlparse(url).netloc.lower()
    if not domain:
        return "T3"
    if any(d in domain for d in GOV_DOMAINS):
        return "T0"
    if brand_zh and _is_brand_domain(domain, brand_zh):
        return "T0"
    if any(d in domain for d in OTA_DOMAINS):
        return "T1"
    if any(d in domain for d in REVIEW_DOMAINS):
        return "T2"
    if any(d in domain for d in UGC_DOMAINS):
        return "T3"
    return "T3"


def _is_brand_domain(domain: str, brand_zh: str) -> bool:
    """域名是否含品牌英文名（查 brand_domains 映射表）。"""
    kb = get_knowledge_loader()
    for item in kb.load_category("brand_domains"):
        if item.get("zh") == brand_zh or brand_zh in item.get("zh", ""):
            if any(kw in domain for kw in item.get("domain_keywords", [])):
                return True
    return False
