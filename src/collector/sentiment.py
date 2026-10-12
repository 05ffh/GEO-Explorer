"""负面率计算：舆情总量 → 负面关键词命中 → 负面率 + 8 类主题分布。

负面判定铁律：只看关键词命中，不看甲方档位。
关键词只做粗筛召回，**负面终判由主 agent 做**，标准 = 是否真正影响酒旅消费者
是否来甲方酒店消费（硬伤如蟑螂/血迹/辱骂/偷拍/到店无房算负面；轻微瑕疵如
房间小/太吵/位置偏不揪字眼，不算）。`negated` 是信号不是裁决，系统只标记。
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from src.industry_knowledge.loader import get_knowledge_loader

_NEGATION_CHARS = "不没无未非别莫勿欠少"
_NEGATION_WINDOW = 3  # 关键词前 3 字符内的否定字 → negated 信号（窗口启发式）

# 评分摘要/好评页特征（"评分 4.8/5""住客点评""惊艳"）——若命中负面词但无强负面证据，多为误判
_RATING_SUMMARY = re.compile(r"\d(?:\.\d)?\s?/\s?5|评分|住客点评|惊艳|超棒|好评|点赞")
# 强负面词：出现即真负面（不受评分摘要抑制）
_STRONG_NEG_WORDS = (
    "投诉", "差评", "不退", "辱骂", "偷拍", "蟑螂", "血迹", "欺诈", "拒不", "驱逐",
    "擅自经营", "取消会籍", "态度恶劣", "押金", "脏乱", "食物中毒", "火灾",
)


@dataclass
class NegativeHit:
    theme: str
    keyword: str
    negated: bool


def classify_negative(text: str) -> list[NegativeHit]:
    """命中 8 类负面主题 → 返回命中列表（含 negated 信号）。每主题只记一次。

    评分摘要抑制（2026-09-01 细筛优化）：评分页/好评页（"设施 8.4/5"）若命中负面词
    但无强负面证据，判为非负面（关键词只作召回，误判交主 agent 终判排除）。
    """
    if not text:
        return []
    if _RATING_SUMMARY.search(text) and not any(w in text for w in _STRONG_NEG_WORDS):
        return []
    hits: list[NegativeHit] = []
    for item in get_knowledge_loader().load_category("negative_theme_keywords"):
        theme = item["id"]
        for kw in item.get("keywords", []):
            idx = text.find(kw)
            if idx < 0:
                continue
            prefix = text[max(0, idx - _NEGATION_WINDOW):idx]
            hits.append(NegativeHit(theme=theme, keyword=kw, negated=any(c in prefix for c in _NEGATION_CHARS)))
            break
    return hits


def compute_negative_rate(results) -> dict:
    """结果集 → {total, negative_count, rate, themes}。URL 去重后计数。

    分母 = 去重后品牌信息总量，分子 = 命中负面关键词的条数。
    只看 snippet 摘要，不看全文 → 负面率是下界（ponytail: 全文情绪分析属 P4）。
    """
    seen: set[str] = set()
    total = 0
    negative = 0
    theme_counter: Counter[str] = Counter()

    for r in results:
        url = _field(r, "url")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        total += 1
        hits = classify_negative(_field(r, "snippet"))
        if hits:
            negative += 1
            for h in hits:
                theme_counter[h.theme] += 1

    return {
        "total": total,
        "negative_count": negative,
        "rate": round(negative / total, 4) if total else 0.0,
        "themes": dict(theme_counter),
    }


def combine_negative_rate(store_rate: float, brand_rate: float) -> float:
    """合成负面率：门店级 0.8 + 品牌级 0.2（spec 4.6）。

    brand_rate 应为主 agent 终判后、已做地区过滤（跨省算/跨国不算）的品牌级负面率。
    """
    return round(0.8 * store_rate + 0.2 * brand_rate, 4)


def _field(r, name: str) -> str:
    """兼容 ORM 对象与 dict。"""
    if isinstance(r, dict):
        return r.get(name, "") or ""
    return getattr(r, name, "") or ""
