"""平台信源调性校准（spec ⑪ P0-B）：建各平台回答基线，区分"甲方内容不足"vs"平台风格/结构性"。

数据就绪：纯 judgments 聚合（hotels_recommended / answer_tier_distribution / platform_rate /
competitor_visibility），无外部依赖、无新采集——回应甲方"文心 0% 是内容不足还是平台风格"。

平台基线字段：
- avg_hotels_listed：每题平均列几家酒店（只答区域=0，未判定题不计）→ 平台回答密度
- high_end_ratio：推荐中甲方档位及以上占比（**直接按题聚合，缺失档计 0**，不依赖
  platform_profile 的分母缺陷）→ 平台爱不爱推甲方档位
- hit_rate：甲方命中率
- main_band_avg_rate：国际五星竞对平均被推率（competitor_visibility）→ 平台给甲方档位多少位置

解读（确定性，不派子 agent，spec ⑪"系统确定性聚合"）：低命中平台按"平台给不给甲方档位位置"分流：
- 平台回答简短（avg_hotels_listed 少）→ 平台风格（铺信源方向）
- 平台不推甲方档位（high_end_ratio 低）→ 结构性档位（铺信源方向）
- 平台列充分+推甲方档位+竞对被推但甲方 0 → 甲方内容不足（真劣势，对标竞对）
- 平台列充分+推甲方档位但竞对也低 → 结构性（该档整体未被推）
- 甲方档位未知 / 无竞对数据 → 数据不足态（tier_unknown / no_band_data），不误判方向

# ponytail: 解读阈值（稀疏<3 家、档位占比<30%、竞对≥30%）是经验值起步，多平台实测后微调。
"""
from __future__ import annotations

from datetime import datetime

from src.collector.judgment import LAYER_ATTRIBUTION

# 档位顺序（>= 甲方档位算"推甲方档位"）
TIER_ORDER = ["经济", "中端", "中高端", "高端", "豪华"]

# 解读阈值（经验值，多平台实测可调）
PLATFORM_SPARSE_THRESHOLD = 3.0     # 每题平均列 < 3 家 = 平台回答简短
HIGH_END_RATIO_THRESHOLD = 0.3      # 甲方档位及以上占比 < 30% = 平台不推甲方档位
BAND_PUSH_THRESHOLD = 0.3           # 国际五星竞对平均被推率 ≥ 30% = 平台愿意推甲方档位
CLIENT_HIT_HEALTHY = 0.5            # 甲方命中率 ≥ 50% = 正常

_READING_CN = {
    "normal": "正常（甲方被推荐，无调性阻碍）",
    "platform_sparse": "平台风格（回答简短少列酒店，甲方 0% 是平台少列，非甲方个体）→ 铺信源",
    "platform_tier_mismatch": "结构性档位（平台不推甲方档位，甲方档位占比低）→ 铺信源",
    "client_content_gap": "甲方内容不足（平台列充分+推甲方档位+国际五星竞对被推，但甲方未上榜）→ 对标竞对补内容",
    "structural": "结构性（平台列充分+推甲方档位，但该档整体未被推，竞对也低）→ 铺信源",
    "tier_unknown": "数据不足（甲方档位未知/表外，无法判断平台是否推甲方档位）→ 先补定位档位",
    "no_band_data": "数据不足（无竞对数据，无法判断竞对参照）→ 先 write_competitor 补竞对",
}


def _high_end_ratio_from_judgments(judgments: list[dict], client_tier: str) -> float | None:
    """直接按题聚合"甲方档位及以上"占比（对抗审查 HIGH 修复：缺失档计 0，分母统一）。

    语义：平台列出的酒店里，甲方档位及以上占多少（只对有档位分布的题求和，
    只答区域题无档位不入分母——它没列酒店，无从谈档位）。表外档位返回 None。
    """
    if not client_tier:
        return None
    try:
        idx = TIER_ORDER.index(client_tier)
    except ValueError:
        return None
    above = set(TIER_ORDER[idx:])
    total = high = 0
    for j in judgments:
        dist = j.get("answer_tier_distribution") or {}
        q_total = sum(dist.values())
        if q_total == 0:
            continue
        total += q_total
        high += sum(v for t, v in dist.items() if t in above)
    return round(high / total, 4) if total else 0.0


def _read_platform(hit_rate: float, avg_hotels: float,
                   high_ratio: float | None, band_avg: float | None) -> str:
    """确定性解读（优先级：正常 > 平台稀疏 > 数据不足态 > 档位错配 > 甲方内容缺 > 结构性）。"""
    if hit_rate >= CLIENT_HIT_HEALTHY:
        return "normal"
    if avg_hotels < PLATFORM_SPARSE_THRESHOLD:
        return "platform_sparse"
    if high_ratio is None:
        return "tier_unknown"
    if band_avg is None:
        return "no_band_data"
    if high_ratio < HIGH_END_RATIO_THRESHOLD:
        return "platform_tier_mismatch"
    if band_avg >= BAND_PUSH_THRESHOLD:
        return "client_content_gap"
    return "structural"


def compute_platform_baseline(measurement: dict, client_tier: str | None = None) -> dict:
    """平台基线表（确定性聚合，spec ⑪ P0-B）。

    读 judgments（hotels_recommended 长度 / answer_tier_distribution）+ platform_rate +
    competitor_visibility.platforms（国际五星竞对平均被推率）。返回 {平台: {字段 + reading}}。
    """
    competitor_vis = measurement.get("competitor_visibility", {}).get("platforms", {})
    has_band = bool(competitor_vis)
    out: dict[str, dict] = {}
    for pl, info in measurement.get("platforms", {}).items():
        answered = [
            j for j in info.get("judgments", [])
            if j.get("layer") != LAYER_ATTRIBUTION
            and j.get("reason") != "error"
            and j.get("recommendation") is not None  # 排除未判定（partial run 不拉低均值）
        ]
        listed = [len(j.get("hotels_recommended") or []) for j in answered]
        avg_h = round(sum(listed) / len(listed), 2) if listed else 0.0
        hit_rate = info.get("platform_rate", {}).get("hit_rate", 0.0)
        high_ratio = _high_end_ratio_from_judgments(answered, client_tier or "")
        band_avg = competitor_vis.get(pl, {}).get("main_avg_rate") if has_band else None
        reading = _read_platform(hit_rate, avg_h, high_ratio, band_avg)
        out[pl] = {
            "avg_hotels_listed": avg_h,
            "high_end_ratio": high_ratio,
            "hit_rate": hit_rate,
            "main_band_avg_rate": band_avg,
            "reading": reading,
            "note": _READING_CN[reading],
        }
    return out


def apply_review(baseline: dict, patch: dict, reviewer: str = "main_agent") -> dict:
    """主 agent 复核（spec ⑪ P0-B 复核门）：改判/确认 reading + 留审计记录。

    patch = {平台: {"reading": "...", "reason": "..."}}——只在 patch 里的平台被核；
    reading 与系统先验一致 → status=confirmed；不同 → status=revised（记录原因）。
    返回 baseline（原地改）。非法 reading 抛 ValueError。
    """
    if not isinstance(patch, dict):
        raise ValueError("复核 patch 顶层必须是 {平台: {reading, reason}}")
    unknown = [pl for pl in patch if pl not in baseline]
    if unknown:
        raise ValueError(f"复核 patch 含未知平台 {unknown}（合法：{sorted(baseline)}）")
    for pl, rev in patch.items():
        if not isinstance(rev, dict):
            raise ValueError(f"{pl}: 复核值必须 dict {{reading, reason}}，收到 {type(rev).__name__}")
        reading = rev.get("reading")
        reason = rev.get("reason") or ""
        if reading not in _READING_CN:
            raise ValueError(f"{pl}: 非法 reading {reading!r}（合法：{sorted(_READING_CN)}）")
        sys_reading = baseline[pl]["reading"]
        if reading != sys_reading and not reason.strip():
            raise ValueError(f"{pl}: 改判必须留 reason（reading 从 {sys_reading} 改为 {reading}）")
        baseline[pl]["review"] = {
            "status": "revised" if reading != sys_reading else "confirmed",
            "system_reading": sys_reading,
            "reviewed_reading": reading,
            "reviewer": reviewer,
            "reason": reason,
            "reviewed_at": datetime.now().isoformat(timespec="seconds"),
        }
        baseline[pl]["reading"] = reading
        baseline[pl]["note"] = _READING_CN[reading]
    return baseline
