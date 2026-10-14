"""命中率计算（spec 3.2 + 11.9 判定重构，2026-09-04 A-3 重构）。

新口径：二分命中率（hit=recommendation==recommend）+ 子场景首推/均排 + 分母净化
（has_hotel_recommendations）+ 未命中结构（真劣势/结构性/题面错位/提及/排除）。
有效题（分母）= 命中层 has_hotel_recommendations=true 的题（含结构性未命中——绝对
可见度口径，same_tier_pushed 只做归因分层、不改命中率）。
"""
from __future__ import annotations


def compute_platform_rate(
    judgments: list[dict],
    tier_word_questions: set[str] | None = None,
) -> dict:
    """单平台切面（spec 11.9 二分口径 + apply 核定 2026-09-04）。

    有效题（分母）= 命中层 has_hotel_recommendations=true 且已判定（recommendation 非 None）
    且非 error 的题。error/未判定/无酒店推荐单独统计，不进分母。
    hit = recommendation==recommend（二分，不再位置截断，spec 11.9 决策点 1）。
    首推 = scene.rank_in_scene==1；均排 = recommend 题的 scene.rank_in_scene 均值。
    未命中结构（A4 落地，2026-09-10 口径修正）：真劣势=absent+**推荐名单**推了甲方同档竞技场
    酒店（甲方档位+更高一档，只读 hotels_recommended 推荐名单，提及名单不计）；结构性=absent+
    推荐名单未推同档竞技场酒店；题面错位=absent+未推同档竞技场酒店+题目带档位词
    （tier_word_questions 传入才细分，未传并回结构性）。
    """
    from .judgment import LAYER_ATTRIBUTION, RECOMMEND, ABSENT, MENTION, EXCLUDE

    valid = [
        j for j in judgments
        if j.get("layer") != LAYER_ATTRIBUTION
        and j.get("has_hotel_recommendations")
        and j.get("recommendation") is not None
        and j.get("reason") != "error"
    ]
    undecided = sum(1 for j in judgments if j.get("recommendation") is None and j.get("reason") != "error")
    no_hotel_rec = sum(1 for j in judgments if j.get("has_hotel_recommendations") is False)

    hit_count = sum(1 for j in valid if j["recommendation"] == RECOMMEND)
    # 首推 = recommend 且子场景 rank1（过滤非 recommend：rank 只对被推荐题有意义，
    # 防历史/他径写入的 mention+rank 虚增首推率）。方案 A 局限：AI 分"首推/备选"层时
    # 首推率应只计首推层 rank1——当前 scene 无层级字段，备选层 rank1 也会计入，遇该场景需落地
    first_count = sum(1 for j in valid if j["recommendation"] == RECOMMEND and (j.get("scene") or {}).get("rank_in_scene") == 1)
    ranks = [
        j["scene"]["rank_in_scene"]
        for j in valid
        if j["recommendation"] == RECOMMEND and (j.get("scene") or {}).get("rank_in_scene") is not None
    ]

    miss = {"true_disadvantage": 0, "structural": 0, "question_mismatch": 0, "mention": 0, "exclude": 0}
    for j in valid:
        rec = j["recommendation"]
        if rec == RECOMMEND:
            continue
        same = bool(j.get("same_tier_pushed"))
        has_tier = tier_word_questions is not None and j.get("question_id") in tier_word_questions
        if rec == ABSENT:
            if same:
                miss["true_disadvantage"] += 1
            else:
                miss["question_mismatch" if has_tier else "structural"] += 1
        elif rec == MENTION:
            miss["mention"] += 1
        elif rec == EXCLUDE:
            miss["exclude"] += 1

    denom = len(valid)
    return {
        "total": len(judgments),
        "valid": denom,
        "undecided": undecided,
        "no_hotel_rec": no_hotel_rec,
        "hit_count": hit_count,
        "hit_rate": round(hit_count / denom, 4) if denom else 0.0,
        "first_rate": round(first_count / denom, 4) if denom else 0.0,
        "avg_rank": round(sum(ranks) / len(ranks), 2) if ranks else None,
        "avg_rank_insufficient": len(ranks) < 3,
        "miss_structure": miss,
    }


def compute_overall(platform_rates: dict[str, dict]) -> dict:
    """整体命中率 = 四平台命中率的算术平均（spec 决策 8）。

    platform_rates = {"deepseek": {...}, "kimi": {...}, ...}
    返回 {"overall_hit_rate", "platform_hit_rates"}。
    """
    rates = [r["hit_rate"] for r in platform_rates.values() if r["total"] > 0]
    return {
        "overall_hit_rate": round(sum(rates) / len(rates), 4) if rates else 0.0,
        "platform_hit_rates": {k: v["hit_rate"] for k, v in platform_rates.items()},
    }


# 负面折损系数 β（spec 4.5 双重惩罚修正，经验值起步、人工微调）：
# 命中率本身已部分反映口碑（AI 少推负面多的酒店），全额乘负面率会双重惩罚 → β<1。
VISIBILITY_NEGATIVE_BETA = 0.7


def effective_visibility(
    hit_rate: float,
    combined_negative_rate: float,
    beta: float = VISIBILITY_NEGATIVE_BETA,
) -> float:
    """有效可见度 = 命中率 × (1 − β×负面率合成)（spec P3 行 + 双重惩罚修正）。

    命中率 = AI 推荐甲方的概率（原始可见度，spec 决策 4）；负面率合成 = 0.8×门店+0.2×品牌
    （spec 4.6，combine_negative_rate 产出）。β<1 承认命中率已含部分负面影响，
    避免"负面既压低命中率、又额外打折"的双重惩罚（2026-09-01 数据分析师优化）。
    """
    hit_rate = max(0.0, min(1.0, hit_rate))
    combined_negative_rate = max(0.0, min(1.0, combined_negative_rate))
    return round(max(0.0, min(1.0, hit_rate * (1 - beta * combined_negative_rate))), 4)


_AGENT_TASK = (
    "命中语义判定：判 recommendation（推荐/提及/排除/未出现）+ scene（子场景维度/值/子场景内排名/数）"
    " + referred_content + has_hotel_recommendations + hotels_recommended[推荐名单] + hotels_mentioned[提及名单]。"
    "档位/竞对（same_tier_pushed/answer_tier_distribution）由系统查 brand_domains 派生，子 agent 不判。"
)

# 归因层任务（2026-09-13 对抗审查：agent_tasks 原先全按命中语义标，归因题被误导）
_ATTRIBUTION_AGENT_TASK = (
    "归因劣势提取（P1-②）：读甲方 vs 竞品 对比回答，提取甲方劣势维度"
    "（服务/设施/价格/位置/品牌/餐饮/其他），带接地分类（true_disadvantage=甲方没有→对标竞对 / "
    "client_has_unreferenced=甲方有但 AI 未引用→铺内容），每条带 AI 原话证据。"
)


def _persona_of(question_id: str) -> str | None:
    """从 question_id 解析人群（hit_family_size → family）。归因层同构（attr_business → business）。"""
    parts = (question_id or "").split("_")
    return parts[1] if len(parts) > 1 else None


def compute_persona_rates(judgments: list[dict]) -> dict:
    """分人群命中率（spec 3.0 分人群切面，A-3 决策点 A）。口径同 compute_platform_rate。"""
    from .judgment import LAYER_ATTRIBUTION, RECOMMEND

    by_persona: dict[str, dict] = {}
    for j in judgments:
        if (
            j.get("layer") == LAYER_ATTRIBUTION
            or j.get("recommendation") is None
            or j.get("reason") == "error"
            or not j.get("has_hotel_recommendations")
        ):
            continue
        persona = _persona_of(j.get("question_id") or "")
        if not persona:
            continue
        d = by_persona.setdefault(persona, {"valid": 0, "hit": 0})
        d["valid"] += 1
        if j["recommendation"] == RECOMMEND:
            d["hit"] += 1
    return {
        p: {"valid": d["valid"], "hit": d["hit"], "hit_rate": round(d["hit"] / d["valid"], 4) if d["valid"] else 0.0}
        for p, d in by_persona.items()
    }


def aggregate_platform_profile(judgments: list[dict]) -> dict:
    """平台档位画像：每题 answer_tier_distribution 归一化成占比 → 跨题平均。

    替代人工写死的 platform_source_profile 三维（spec 11.9 评审修正：画像 = judgment 聚合的
    观测结果，随每 run 累积变准，避免单次观测偏差）。占比归一化避免题量大的题主导。
    """
    per_tier: dict[str, list[float]] = {}
    for j in judgments:
        dist = j.get("answer_tier_distribution")
        if not dist:
            continue
        total = sum(dist.values())
        if not total:
            continue
        for tier, count in dist.items():
            per_tier.setdefault(tier, []).append(count / total)
    return {t: round(sum(v) / len(v), 4) for t, v in per_tier.items()} if per_tier else {}


def aggregate_content_assets(judgments: list[dict]) -> list[dict]:
    """内容资产清单：跨题汇总 referred_content → 去重计频。

    # ponytail: 措辞变体（"奶龙亲子房"vs"奶龙主题亲子房"）字符串去重不彻底、计频偏低——
    # 子 agent 判定时用统一词（A-2 prompt 规范），此聚合只做字符串去重，报告注明近似。
    """
    from collections import Counter

    counter: Counter[str] = Counter()
    for j in judgments:
        for item in j.get("referred_content") or []:
            if item:
                counter[item] += 1
    return sorted(({"content": k, "count": v} for k, v in counter.items()), key=lambda x: -x["count"])


def finalize_measurement(m: dict, tier_word_questions: set[str] | None = None) -> int:
    """重算 measurement 切面 + overall + miss_structure + status，返回未判题数（needs_agent）。

    platform_rate / agent_tasks / miss_structure 均从 judgments 单一来源重建（不保留旧值），
    finalize_hit --apply 回填与 run_measure 补测共用，保证两处判定一致、无残留。
    status：仍存 needs_agent 题 → partial；否则 complete。
    """
    from .judgment import LAYER_ATTRIBUTION
    platforms = m.setdefault("platforms", {})
    tasks: list[dict] = []
    for info in platforms.values():
        info["platform_rate"] = compute_platform_rate(info.get("judgments", []), tier_word_questions=tier_word_questions)
        for j in info.get("judgments", []):
            if j.get("needs_agent"):
                tasks.append({
                    "question_id": j["question_id"],
                    "question": j.get("question", ""),
                    "task": _ATTRIBUTION_AGENT_TASK if j.get("layer") == LAYER_ATTRIBUTION else _AGENT_TASK,
                })
    m["agent_tasks"] = tasks
    m["overall"] = compute_overall({p: i["platform_rate"] for p, i in platforms.items()})
    m["miss_structure"] = {
        k: sum(i["platform_rate"]["miss_structure"][k] for i in platforms.values())
        for k in ("true_disadvantage", "structural", "question_mismatch", "mention", "exclude")
    }
    # A-3b 聚合：平台画像 / 内容资产 / 分人群命中率（judgment 聚合观测，spec 11.9）
    m["platform_profile"] = {p: aggregate_platform_profile(info.get("judgments", [])) for p, info in platforms.items()}
    m["content_assets"] = aggregate_content_assets([j for i in platforms.values() for j in i.get("judgments", [])])
    m["persona_rates"] = {p: compute_persona_rates(info.get("judgments", [])) for p, info in platforms.items()}
    m["status"] = "partial" if tasks else "complete"
    return len(tasks)


def close_measurement(
    measurement: dict,
    competitors: list | None = None,
    sentiment: dict | None = None,
    city: str | None = None,
    client_tier: str | None = None,
) -> int:
    """盖章（spec ⑫ 唯一收口点）：从已判定 judgments 一次算齐全部派生字段，钉住输入。

    = finalize_measurement（命中率/首推/均排/未命中/画像/内容资产/分人群/status）
    + effective_visibility（钉负面率合成，防双重惩罚 β=0.7）
    + competitor_visibility（钉竞对，主/次相对可见度）
    + platform_baseline（钉平台信源调性，spec ⑪ P0-B，需 client_tier 定位"甲方档位"）

    派生指标只在盖章时算一次，之后 sealed 版本只读、下游永不重派生（竞对/负面率输入已
    经派生进 competitor_visibility/effective_visibility，无需另钉原始清单）。
    返回未判题数（needs_agent，>0 → status=partial）。
    """
    from .competitor_visibility import compute_competitor_visibility
    from .platform_baseline import compute_platform_baseline
    from .sentiment import combine_negative_rate

    # 防 stale（spec ⑫ sealed 单一来源）：派生字段一律按本次输入重算，输入缺则移除不残留旧值。
    # （rejudge 时若竞对/负面率被清空，旧 competitor_visibility/effective_visibility 不得带进新版本）
    measurement.pop("effective_visibility", None)
    measurement.pop("effective_visibility_status", None)
    measurement.pop("negative_rate_combined", None)
    measurement.pop("competitor_visibility", None)
    # 复核记录是人审结果（对抗审查 HIGH）：rejudge 重算会覆盖 reading，但复核记录保留并标 stale——
    # 下游能看到"曾复核过，重判后可能过期"，不静默清掉人审痕迹。
    import copy as _copy
    old_reviews = {
        pl: _copy.deepcopy((entry or {}).get("review"))
        for pl, entry in (measurement.get("platform_baseline") or {}).items()
    }
    measurement.pop("platform_baseline", None)

    # 真劣势锚定（2026-09-10 修正）：same_tier_pushed = 推荐名单里推了钉住的主/次竞对。
    # 取代档位范围派生（apply 阶段无竞对清单，seal 处唯一派生）——甲方被钉住竞对挤掉 = 真劣势，
    # 仅推非钉住高端酒店 ≠ 真劣势。归一化全名匹配（复用 competitor_in_hotels，防"喜来登"误配）。
    from .competitor_visibility import pinned_competitor_pushed
    for info in measurement.get("platforms", {}).values():
        for j in info.get("judgments", []):
            j["same_tier_pushed"] = pinned_competitor_pushed(
                j.get("hotels_recommended") or [], competitors or [], city)

    remaining = finalize_measurement(measurement)
    store_s, brand_s = {}, {}
    if sentiment:
        store_s = sentiment.get("store_level", {}) or {}
        brand_s = sentiment.get("brand_level", {}) or {}
    if store_s.get("rate") is not None:
        # 单档（无品牌级）→ combine 直接返回门店级；品牌级在则按 8:2。
        combined = combine_negative_rate(store_s["rate"], brand_s.get("rate"))
        measurement["effective_visibility"] = effective_visibility(
            measurement["overall"]["overall_hit_rate"], combined)
        brand_ok = (brand_s.get("status") == "confirmed") if brand_s else True
        measurement["effective_visibility_status"] = (
            "confirmed" if store_s.get("status") == "confirmed" and brand_ok
            else "preliminary")
        measurement["negative_rate_combined"] = combined  # 钉负面率输入（审计/复算用）
    if competitors:
        measurement["competitor_visibility"] = compute_competitor_visibility(
            measurement, competitors, city)
    if client_tier:
        measurement["platform_baseline"] = compute_platform_baseline(measurement, client_tier)
        # 重挂旧复核记录：reading 与重算后的系统 reading 不一致 → 标 stale（需重复核）
        for pl, review in old_reviews.items():
            if review and pl in measurement["platform_baseline"]:
                entry = measurement["platform_baseline"][pl]
                entry["review"] = review
                entry["review"]["stale"] = review.get("reviewed_reading") != entry["reading"]
    # 表外告警（brand_domains 信任①）：推荐名单里查不到档位的酒店——档位/真劣势判定盲区，
    # 显式暴露（sealed，报告层展示"N 家酒店档位未知"），不静默。只列推荐名单（派生输入），
    # 提及名单不进判定。无表外则移除不残留。
    from .tier import get_brand
    unknown = sorted({
        h
        for info in measurement.get("platforms", {}).values()
        for j in info.get("judgments", [])
        for h in (j.get("hotels_recommended") or [])
        if get_brand(h, city) is None
    })
    if unknown:
        measurement["unknown_tier_hotels"] = unknown
    else:
        measurement.pop("unknown_tier_hotels", None)
    return remaining
