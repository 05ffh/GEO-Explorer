"""报告数据提取（P5 报告层）：从 V6 快照提取报告所需事实数字。

只产数字/清单，不产叙述——业务叙述由主 agent 撰写后经 narrative 传入。
场景分组读 question_templates_client.yaml 的 scenario 字段（主 agent 标注的甲方专属场景）。
"""
from __future__ import annotations

_THEME_CN = {"hygiene": "卫生", "service": "服务", "dining": "餐饮", "price": "价格"}


def _scenario_map() -> dict[str, str]:
    from src.industry_knowledge.loader import get_knowledge_loader
    try:
        items = get_knowledge_loader().load_category("question_templates_client")
    except Exception:
        return {}
    return {it["id"]: it["scenario"] for it in items if it.get("scenario")}


def _scenes(platforms: dict, scenario_of: dict[str, str]) -> list[dict]:
    """按场景聚合命中层：每场景的题面 + 甲方被推荐次数/有效次数。"""
    agg: dict[str, dict] = {}
    for info in platforms.values():
        for j in info.get("judgments", []):
            if j.get("layer") != "hit":
                continue
            sc = scenario_of.get(j.get("question_id") or "")
            if not sc:
                continue
            d = agg.setdefault(sc, {"name": sc, "questions": [], "valid": 0, "hit": 0})
            if j.get("question") and j["question"] not in d["questions"]:
                d["questions"].append(j["question"])
            if j.get("has_hotel_recommendations") and j.get("recommendation") is not None:
                d["valid"] += 1
                if j.get("recommendation") == "recommend":
                    d["hit"] += 1
    for d in agg.values():
        d["hit_rate"] = round(d["hit"] / d["valid"], 4) if d["valid"] else 0.0
    return list(agg.values())


def _count_facts(facts_json) -> int:
    if not isinstance(facts_json, dict):
        return 0
    return sum(len(v) for v in (facts_json.get("facts") or {}).values() if isinstance(v, list))


def build_report_data(run) -> dict:
    m = run.measurement_json or {}
    cv = m.get("competitor_visibility") or {}
    bands = cv.get("bands") or {}
    comp: dict[str, list] = {"main": [], "secondary": []}
    for band in ("main", "secondary"):
        for mem in ((cv.get("overall") or {}).get(band) or {}).get("members", []):
            comp[band].append({
                "name": mem["name"], "rate": mem.get("overall_rate"),
                "platform_rates": mem.get("platform_rates") or {},
                "band": bands.get(mem["name"], band),
            })
    sent = (run.sentiment_json or {}).get("store_level") or {}
    return {
        "brand": getattr(run, "brand", "") or m.get("brand", ""),
        "city": getattr(run, "city", "") or m.get("city", ""),
        "collected_at": m.get("collected_at", ""),
        "question_count": len(m.get("question_fingerprint") or []),
        "hit_rate": (m.get("overall") or {}).get("overall_hit_rate"),
        "platform_hit_rates": (m.get("overall") or {}).get("platform_hit_rates") or {},
        "effective_visibility": m.get("effective_visibility"),
        "negative_rate": m.get("negative_rate_combined"),
        "miss_structure": m.get("miss_structure") or {},
        "competitors": comp,
        "scenes": _scenes(m.get("platforms") or {}, _scenario_map()),
        "attribution": m.get("attribution_dims") or {},
        "content_assets": m.get("content_assets") or [],
        "sentiment": {
            "rate": sent.get("rate"), "total": sent.get("total"),
            "negative_count": sent.get("negative_count"),
            "themes": {_THEME_CN.get(k, k): v for k, v in (sent.get("themes") or {}).items()},
        },
        "gt_facts_count": _count_facts(run.gt_facts_json),
        "cdp_facts_count": _count_facts(run.cdp_facts_json),
        "cdp_consistency": (run.cdp_facts_json or {}).get("consistency") or {},
        "cdp_stale": (run.cdp_facts_json or {}).get("stale_facts") or {},
    }
