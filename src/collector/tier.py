"""档位评定（spec 3.1.1，2026-09-01 重设计）：品牌梯队(ADR 校准) + ADR 区间 + 星级下限/上限。

档位体系：经济 / 中端 / 中高端 / 高端 / 豪华（去顶奢，顶奢并入豪华）。
判定链：甲方指定 > 品牌梯队（门店 ADR 偏离参考带 → 市场价落点）> ADR 区间 > 星级（下限/上限）。
品牌表存双字段：tier（品牌行政档位，跨城市稳定）+ adr_range（中国市场典型 ADR 带，供校准）。
门店 ADR 低于品牌参考带 → 用市场价落点（福州洲际 700<800 → 高端，豪华品牌不虚高）；
门店 ADR 高于参考带 → 同理用市场价落点（弱品牌高溢价按市场价升）。
来源铁律：ADR/星级只取联网搜索（search，带 URL），AI 回答措辞不参与定档。
"""
from __future__ import annotations

import re

from src.industry_knowledge.loader import get_knowledge_loader

# 间隔号归一化（匹配前统一）：本地酒店名可能带"·/・/•/∙/．"等变体（四季·悦城 vs 四季悦城），
# 子串匹配前去掉，避免同店因间隔号变体匹配失败或误配到父品牌（四季悦城 vs 国际四季）
_SEP = re.compile(r"[·•・∙．]")

# 档位 → 消费者自然措辞（命中层模板 + 竞品查询词用，spec 3.1.1 档位措辞映射）
TIER_WORD = {
    "经济": "性价比高的",
    "中端": "舒适的",
    "中高端": "中高档的",
    "高端": "高端的",
    "豪华": "五星级的",
}

# 档位 → 价格带上限（命中层预算题 {预算} 变量用，保证甲方在预算内）
TIER_BUDGET = {
    "经济": "300",
    "中端": "500",
    "中高端": "800",
    "高端": "1500",
    "豪华": "2500",
}

# 无品牌时 ADR 价格分界（从高到低，2026-09-01 按福州真实市场校准；等于分界值归高档）。
# 福州国际五星日常 ADR 600-900（洲际700/凯宾750/希尔顿850），中高端精品 400-700（臻庭550/榕棠550/水部悦容600）——
# 两档 ADR 重叠，纯 ADR 分不开，靠品牌/星级信号精修（品牌 adr_range 校准 + 星级 clamp）。分界：经济<250/中端250-400/中高端400-700/高端700-1500/豪华>=1500。
_ADR_BOUNDS = [(1500, "豪华"), (700, "高端"), (400, "中高端"), (250, "中端"), (0, "经济")]

# 星级 → 档位（兜底 + clamp 目标；下限保护/上限限制见 _clamp_star）
_STAR_TIER = {"五星": "高端", "四星": "中端", "三星": "经济"}

# 星级输入变体归一化（主 agent 提取值可能带"级/星"后缀或阿拉伯数字）
_STAR_NORM = {
    "五星级": "五星", "五星": "五星", "5星": "五星", "5星级": "五星",
    "四星级": "四星", "四星": "四星", "4星": "四星", "4星级": "四星",
    "三星级": "三星", "三星": "三星", "3星": "三星", "3星级": "三星",
}

_ORDER = ["经济", "中端", "中高端", "高端", "豪华"]


def _tier_by_adr(adr: float) -> str | None:
    for bound, tier in _ADR_BOUNDS:
        if adr >= bound:
            return tier
    return None


def _clamp_star(tier: str, star_rating: str) -> str:
    """星级下限/上限约束：五星≥高端、四星≥中端、三星≤中端。"""
    idx = _ORDER.index(tier)
    if star_rating == "五星" and idx < _ORDER.index("高端"):
        return "高端"
    if star_rating == "四星" and idx < _ORDER.index("中端"):
        return "中端"
    if star_rating == "三星" and idx > _ORDER.index("中端"):
        return "中端"
    return tier


def tier_span(tier: str) -> list[str]:
    """甲方档位 ±1 档（含自身），竞品搜索词多档位召回用。表外档位返回 [tier]。"""
    if tier not in _ORDER:
        return [tier]
    i = _ORDER.index(tier)
    return _ORDER[max(0, i - 1): i + 2]


def get_brand(brand_zh: str, city: str | None = None) -> dict | None:
    """查品牌条目（tier + adr_range + en + region），表外返回 None。

    匹配规则：精确相等，或词库品牌名是输入名的子串。**最长子串优先**——
    子品牌名（"希尔顿欢朋"4字）优先于父品牌（"希尔顿"2字），避免欢朋误判成希尔顿。
    不能用 `brand_zh in item["zh"]`，否则"万豪"会误匹配"JW万豪"。
    city 传入时：本地品牌（带 region）仅本地区匹配，换地区（广州）不误用福州本地品牌。
    city 需与 region 字面一致（"福州市"自动归一为"福州"）。**调用方必须传 city**——
    不传时本地品牌 fail-open 全匹配，跨地区可能误匹配。
    """
    if city:
        city = city.rstrip("市")  # 归一化："福州市"/"福州市" → "福州"，与 region 字面一致
    brand_norm = _SEP.sub("", brand_zh)
    best = None
    for item in get_knowledge_loader().load_category("brand_domains"):
        region = item.get("region")
        if region and city and region != city:
            continue  # 本地品牌，非本地区跳过
        zh = _SEP.sub("", item["zh"])
        if zh == brand_norm or zh in brand_norm:
            # 最长子串优先：比较归一化后长度（避免带间隔号的条目长度虚高）
            if best is None or len(zh) > len(_SEP.sub("", best["zh"])):
                best = item
    return best


def get_brand_tier(brand_zh: str, city: str | None = None) -> str | None:
    """查品牌档位（可传 city 过滤本地品牌地区归属）。"""
    brand = get_brand(brand_zh, city=city)
    return brand["tier"] if brand else None


def derive_tier(
    brand_zh: str,
    client_specified: str | None = None,
    adr: float | None = None,
    star_rating: str | None = None,
    city: str | None = None,
) -> str | None:
    """档位综合评定：甲方指定 > 品牌梯队(ADR 校准) > ADR 区间 > 星级(下限/上限)。

    品牌命中：门店 ADR 偏离品牌 adr_range → 取市场价落点（豪华品牌卖便宜不虚高，
    弱品牌高溢价按市场价升）；ADR 在带内或缺失 → 品牌行政档位。
    星级只在表外做下限保护（五星≥高端/四星≥中端）和上限限制（三星≤中端）。
    city 传入时本地品牌（region）仅本地区匹配（换地区不误用）。
    无法判定返回 None（主 agent 兜底）。
    """
    if client_specified:
        return client_specified

    if star_rating:
        star_rating = _STAR_NORM.get(star_rating, star_rating)

    try:
        adr_f = float(adr) if adr is not None else None
    except (TypeError, ValueError):
        adr_f = None

    brand = get_brand(brand_zh, city=city)
    if brand:
        brand_tier = brand["tier"]
        if brand.get("unconditional"):
            return brand_tier  # 顶级品牌无条件豪华（宝格丽/四季等，不 ADR 校准，spec 3.1）
        adr_range = brand.get("adr_range")
        if adr_f is not None and adr_range and (adr_f < adr_range[0] or adr_f > adr_range[1]):
            adr_tier = _tier_by_adr(adr_f)
            if adr_tier is not None and adr_tier != brand_tier:
                return adr_tier
        return brand_tier

    result = _tier_by_adr(adr_f) if adr_f is not None else None
    if star_rating:
        if result:
            result = _clamp_star(result, star_rating)
        else:
            result = _STAR_TIER.get(star_rating)
    return result
