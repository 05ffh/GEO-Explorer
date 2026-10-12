"""竞对判定（确定性部分，spec 3.1 竞对区域圈层·系统化承载）。

第一性原理：竞对 = 同价格带 × 同客群 × 同城位置，优先级 ADR 带 > 业态 > 位置。
系统判确定性：ADR 带（甲方 ±50%）+ 档位（±1）；ring/format/去重 由主 agent 提供
（地理编码在纯搜索环境下是语义判断，不建 POI 表）。
可靠性：每个候选带判定依据（adr_in_band/tier_in_span/adr_band），主 agent 复核后落库。
"""
from __future__ import annotations

ADR_BAND_RATIO = 0.5

# 竞对 band（甲方视角，spec 3.1 + 3.3，2026-09-07）：国际五星同档 = 主竞争带，
# 本地高端 = 次竞争带。band 是品牌属性（国际连锁 vs 本地），非档位——两类竞对档位都是高端。
COMPETITOR_BAND_MAIN = "main"           # 国际五星同档（香格里拉=国际五星，直接对标对象）
COMPETITOR_BAND_SECONDARY = "secondary" # 本地高端（region 本地品牌，参考维度）


def classify_band(brand: dict | None) -> str | None:
    """竞对 band 分类（确定性，查 brand_domains）。

    高端/豪华 + 无 region → main（国际五星同档）；高端/豪华 + region → secondary（本地高端）；
    表外（get_brand 返回 None）/ 非甲方同档档位 → None（主 agent 兜底）。
    """
    if not brand or brand.get("tier") not in ("高端", "豪华"):
        return None
    return COMPETITOR_BAND_SECONDARY if brand.get("region") else COMPETITOR_BAND_MAIN


def adr_band(client_adr: float, ratio: float = ADR_BAND_RATIO) -> tuple[float, float]:
    """甲方 ADR 带 [下限, 上限] = client_adr * (1±ratio)。"""
    return round(client_adr * (1 - ratio), 1), round(client_adr * (1 + ratio), 1)


def tier_in_span(candidate_tier: str | None, client_tier: str | None) -> bool:
    """候选档位是否在甲方 ±1 档（含自身）。任一档位未定 → False。"""
    if not candidate_tier or not client_tier:
        return False
    from src.collector.tier import tier_span
    return candidate_tier in tier_span(client_tier)


def filter_competitors(
    candidates: list[dict],
    client_tier: str | None,
    client_adr: float,
    ratio: float = ADR_BAND_RATIO,
) -> list[dict]:
    """确定性过滤候选竞对，标注判定依据（供主 agent 复核）。

    candidates = [{name, adr, tier, ring, format, ...}]（ring/format 由主 agent 提供）。
    返回每候选带 adr_in_band / adr_band / tier_in_span 的结构化列表。
    最终竞对 = 主 agent 复核确认 adr_in_band ∧ tier_in_span 的项。
    """
    lo, hi = adr_band(client_adr, ratio)
    out: list[dict] = []
    for c in candidates:
        adr = c.get("adr")
        out.append({
            **c,
            "adr_in_band": adr is not None and lo <= adr <= hi,
            "adr_band": [lo, hi],
            "tier_in_span": tier_in_span(c.get("tier"), client_tier),
        })
    return out


def select_primary(
    competitors: list[dict],
    client_tier: str | None,
    client_adr: float | None = None,
    client_guest: str | None = None,
) -> dict | None:
    """主竞对（P3 归因题对比对象）= 核心圈同档标准酒店中：
    ① 客群重叠（client_guest 匹配 guest_mix）→ ② AI 同场景共现高 → ③ ADR 最近。
    核心无则近邻圈同档；无信号时取顺序第一个（主 agent 写入时按竞争力排序）。

    competitors = 结构化列表 [{name, ring, tier, adr, guest_mix, ai_cooccurrence, ...}]。
    guest_mix / ai_cooccurrence 可选（P3a 后 AI 同场景共现补入）。
    """
    pool = [c for c in competitors if c.get("ring") == "核心" and c.get("tier") == client_tier]
    if not pool:
        pool = [c for c in competitors if c.get("ring") == "近邻" and c.get("tier") == client_tier]
    if not pool:
        return None
    # 标准业态优先（精品/民宿不作主竞对，业态是报告弱标注）
    std = [c for c in pool if c.get("format") in (None, "标准")]
    pool = std or pool
    if client_guest is None and client_adr is None:
        return pool[0]

    def _sort_key(c):
        guest = 1 if (client_guest and c.get("guest_mix") and client_guest in c.get("guest_mix")) else 0
        ai = c.get("ai_cooccurrence") or 0
        if client_adr is not None:
            # 无 ADR 候选降级（否则会被当距离 0 作弊胜出）
            dist = abs(c["adr"] - client_adr) if c.get("adr") is not None else float("inf")
        else:
            dist = 0
        return (guest, ai, -dist)

    return max(pool, key=_sort_key)
