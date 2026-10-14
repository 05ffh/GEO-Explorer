"""报告数据提取（P5 报告层）：从 V6 快照提取报告所需事实数字。

只产数字/清单，不产叙述——业务叙述由主 agent 撰写后经 narrative 传入。
场景分组读 question_templates_client.yaml 的 scenario 字段（主 agent 标注的甲方专属场景）。
"""
from __future__ import annotations

_THEME_CN = {"hygiene": "卫生", "service": "服务", "dining": "餐饮", "price": "价格"}

# AI 引用内容 → 资产主题归并（B2：人工定规则、代码套用，可复现）。按优先级匹配，命中即停。
_CONTENT_THEMES: list[tuple[str, tuple[str, ...]]] = [
    ("米其林星级餐饮（江南灶·融府）", ("江南灶", "米其林", "融府", "淮扬", "狮子头", "佛跳墙", "主厨", "黑珍珠", "闽和南", "葵香鸡", "融小馆")),
    ("宴会与会议（1725㎡ 无柱宴会厅）", ("宴会厅", "婚宴", "婚礼", "会议", "剧院式", "无柱", "桌起", "宴席", "酒席")),
    ("位置与交通（五一广场 / 南门兜地铁）", ("五一广场", "地铁", "南门兜", "三坊七巷", "地址", "地段", "心脏地带", "于山", "乌山", "公里", "步行", "鼓楼区", "交通便利", "地标")),
    ("亲子设施（芽宝乐园 / 亲子房）", ("亲子", "儿童", "芽宝", "带娃", "婴儿床", "家庭房", "游乐", "两大两小")),
    ("康体（室内泳池 / 健身）", ("泳池", "按摩浴缸", "健身", "恒温")),
    ("客房与视野（高层俯瞰）", ("客房", "房型", "天际房", "高层", "俯瞰", "间客房", "床")),
    ("商场配套（八匚汇）", ("八匚汇", "商业体", "商场", "购物")),
    ("口碑评分", ("评分", "口碑", "好评", "TOP1", "评价")),
    ("餐饮（香宫 / 夏宫 / 自助）", ("餐厅", "香宫", "夏宫", "自助", "闽菜", "粤菜", "餐", "酒廊")),
    ("服务（宴会管家 / 服务稳定）", ("服务", "管家", "接待", "周到")),
    ("老牌五星与品牌", ("老牌", "五星", "2005", "开业", "香格里拉集团", "国际品牌", "品牌")),
]


def _group_content_assets(assets: list[dict]) -> list[dict]:
    """AI 引用内容按资产主题归并（B2）：同义措辞合并、主题计数。"""
    tally: dict[str, int] = {}
    other = 0
    for a in assets:
        text = a.get("content") or ""
        n = a.get("count") or 1
        for theme, kws in _CONTENT_THEMES:
            if any(k in text for k in kws):
                tally[theme] = tally.get(theme, 0) + n
                break
        else:
            other += 1
    if other:
        tally["其他"] = tally.get("其他", 0) + other
    return sorted(({"theme": t, "count": c} for t, c in tally.items()), key=lambda x: -x["count"])


def _gt_facts_by_category(gt) -> list[dict]:
    """甲方资产按 8 类计数 + 每类样例一条（让甲方知道"139 条事实"是什么）。"""
    facts = (gt or {}).get("facts") or {}
    out = []
    for cat, items in facts.items():
        if not isinstance(items, list) or not items:
            continue
        sample = items[0]
        out.append({"category": cat, "count": len(items),
                    "sample": sample.get("fact") if isinstance(sample, dict) else str(sample)})
    return sorted(out, key=lambda x: -x["count"])


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


_REC_CN = {"recommend": "推荐", "mention": "引用", "exclude": "排除", "absent": "未提及"}


def _appendix(platforms: dict) -> dict:
    """附录：每平台逐题命中明细（题面 / 判定状态 / 命中摘要）。"""
    out: dict[str, list] = {}
    for pname, info in platforms.items():
        rows = []
        for j in info.get("judgments", []):
            if j.get("layer") != "hit":
                continue
            rec = j.get("recommendation")
            rows.append({
                "question_id": j.get("question_id"),
                "question": j.get("question"),
                "state": _REC_CN.get(rec, "未提及"),
                "summary": "；".join(j.get("referred_content") or []) or "—",
            })
        out[pname] = rows
    return out


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
        "content_themes": _group_content_assets(m.get("content_assets") or []),
        "sentiment": {
            "rate": sent.get("rate"), "total": sent.get("total"),
            "negative_count": sent.get("negative_count"),
            "themes": {_THEME_CN.get(k, k): v for k, v in (sent.get("themes") or {}).items()},
            "items": [{"theme": _THEME_CN.get((it.get("themes") or ["其他"])[0], "其他"),
                       "title": it.get("title", ""), "url": it.get("url", "")}
                      for it in (sent.get("items") or [])],
        },
        "gt_facts_count": _count_facts(run.gt_facts_json),
        "gt_facts_by_category": _gt_facts_by_category(run.gt_facts_json),
        "cdp_facts_count": _count_facts(run.cdp_facts_json),
        "cdp_consistency": (run.cdp_facts_json or {}).get("consistency") or {},
        "cdp_stale": (run.cdp_facts_json or {}).get("stale_facts") or {},
        "appendix": _appendix(m.get("platforms") or {}),
    }
