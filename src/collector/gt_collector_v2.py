"""酒旅 GT 采集器（P2）—— 生成搜索词 → 搜索 → 判 tier → 返回原始材料。

字段值提取由主 agent 辅助（语义判断），系统做确定性部分：
query_builder（搜索词）+ search_fn（搜索，四引擎并列由主 agent 编排）+ source_tier（判 tier）。
可信度 assess_credibility 由主 agent 提取归一化字段值后调用（值依赖语义，不进此骨架）。
"""
from __future__ import annotations

from dataclasses import dataclass

from src.collector.query_builder import build_search_queries, build_sentiment_queries
from src.gt.source_tier import classify_source_tier


@dataclass
class RawMaterial:
    """一条搜索结果（原始材料），带信源 tier 和来源引擎。"""
    field: str          # 字段名（star_rating / adr / store_level / brand_level / ...）
    query: str          # 搜索词
    url: str            # URL
    title: str = ""     # 标题
    snippet: str = ""   # 摘要
    tier: str = "T3"    # 信源 tier（source_tier 判定，事实采集用）
    provider: str = ""  # 来源引擎（tavily/doubao_search/duckduckgo/websearch）
    published_at: str = ""   # 发布时间（时效验证；搜索引擎返回则存，无则空）


async def collect_raw(brand: str, city: str, search_fn) -> list[RawMaterial]:
    """事实采集：生成搜索词 → search_fn(异步) 搜索 → 判 tier → 原始材料。

    search_fn(query) -> list[dict]，dict 含 url/title/snippet（search_all_backends 即是）。
    """
    materials: list[RawMaterial] = []
    for q in build_search_queries(brand, city):
        for r in await search_fn(q["query"]):
            materials.append(RawMaterial(
                field=q["field"],
                query=q["query"],
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("snippet", ""),
                tier=classify_source_tier(r.get("url", ""), brand),
                provider=r.get("provider", ""),
                published_at=r.get("published_at", "") or "",
            ))
    return materials


async def collect_sentiment(brand: str, city: str | None, search_fn) -> list[RawMaterial]:
    """舆情采集（总量）：生成舆情搜索词 → 搜索 → 原始材料。

    field = store_level（门店级，带城市）/ brand_level（品牌级，不带城市）。
    负面率不看 tier（只看关键词命中），故不判 tier。
    """
    materials: list[RawMaterial] = []
    for q in build_sentiment_queries(brand, city):
        for r in await search_fn(q["query"]):
            materials.append(RawMaterial(
                field=q["field"],
                query=q["query"],
                url=r.get("url", ""),
                title=r.get("title", ""),
                snippet=r.get("snippet", ""),
                provider=r.get("provider", ""),
                published_at=r.get("published_at", "") or "",
            ))
    return materials


def group_by_field(materials: list[RawMaterial]) -> dict[str, list[RawMaterial]]:
    """按字段分组原始材料，供主 agent 逐字段提取字段值。"""
    grouped: dict[str, list[RawMaterial]] = {}
    for m in materials:
        grouped.setdefault(m.field, []).append(m)
    return grouped
