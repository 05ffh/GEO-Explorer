"""搜索词生成器 — 把采集规则（field_source_mapping / sentiment_query）变成可执行的搜索词。

诊断单元 = 「品牌 + 地区」的门店实体。生成器读规则，填 {品牌}{城市} 变量，
输出每个字段对应的搜索词列表，供采集器交给四大搜索引擎。
"""
from __future__ import annotations

import logging

from src.collector.tier import derive_tier, TIER_WORD, tier_span
from src.industry_knowledge.loader import get_knowledge_loader

logger = logging.getLogger(__name__)


def build_search_queries(brand: str, city: str) -> list[dict]:
    """读 field_source_mapping 规则，生成事实采集的搜索词列表。

    返回 [{"field": "star_rating", "query": "香格里拉酒店 广州 几星",
           "sources": ["T0", "T1"]}, ...]
    """
    return _build(brand, city, category="field_source_mapping")


def build_sentiment_queries(brand: str, city: str | None = None) -> list[dict]:
    """读 sentiment_query 规则，生成舆情采集（总量）的搜索词列表。

    city 为 None 时只生成品牌级（不带城市）；否则门店级 + 品牌级都生成。
    """
    return _build(brand, city, category="sentiment_query")


def _build(brand: str, city: str | None, category: str) -> list[dict]:
    kb = get_knowledge_loader()
    items = kb.load_category(category)
    queries: list[dict] = []
    for item in items:
        for q in item.get("queries", []):
            if city is None and "{城市}" in q:
                continue  # city=None 时跳过需要城市的 query（如门店级）
            query = q.replace("{品牌}", brand)
            if city is not None:
                query = query.replace("{城市}", city)
            if "{档位词}" in query:
                tier = derive_tier(brand, city=city)
                if tier is None:
                    logger.warning("品牌 %s 档位未定，跳过竞品查询词（需先定档位再单独采竞品）", brand)
                    continue
                # 竞品召回 = 甲方档位 ±1 档（含自身），多档位词展开（spec 3.1 竞对圈层）
                for t in tier_span(tier):
                    word = TIER_WORD.get(t)
                    if word is None:
                        continue  # 表外档位守卫（tier_span 可能返回非标准档位）
                    queries.append({
                        "field": item["id"],
                        "query": query.replace("{档位词}", word),
                        "sources": item.get("sources", []),
                    })
            else:
                queries.append({
                    "field": item["id"],
                    "query": query,
                    "sources": item.get("sources", []),
                })
    return queries
