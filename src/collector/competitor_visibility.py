"""竞对命中率聚合 + 相对可见度（spec 3.3 + ⑧-3，P0-A，2026-09-07）。

确定性聚合（不派子 agent）：从 judgment.hotels_recommended 聚合竞对"被推荐率"，
按 band 分主（国际五星同档，甲方主竞争带）/次（本地高端，次竞争带）两组：
- 主相对可见度（合同主指标）= 甲方命中率 ÷ 主竞对平均被推荐率
- 次相对可见度（参考）= 甲方命中率 ÷ 次竞对平均被推荐率

口径（可审计）：
- 竞对被推荐率 = 竞对出现在 hotels_recommended 的题数 ÷ 甲方有效题数（同分母可同比）
- 有效分母与 hit_rate.compute_platform_rate 完全一致（命中层 + has_hotel + 已判定 + 非 error）
- 甲方命中率 = recommendation==recommend（与名单口径一致：recommend 题甲方必在名单）
- 竞对平均 = 0 → 标"平台未进入甲方档位"（结构性，非 NaN，spec 3.3 边界）

匹配：竞对名归一化（去城市前缀/间隔号/括号内容）→ 子串匹配名单条目。
用竞对全名（去前缀）而非品牌简称，避免"喜来登"误配"福朋喜来登"——
竞对名必须含区分性核心（如"福州中庚喜来登"而非"喜来登"，"福州西湖大酒店"而非"大酒店"）。
甲方自身（香格里拉）的推荐条目不计入任何竞对（competitor_in_hotels 对甲方品牌也匹配，故显式排除）。
# ponytail: normalize_hotel 的"福州/福建"剥除是历史数据兼容兜底（city 传参时已剥 city 前缀）；
# 换地区（广州）时 city=广州 正确剥市名，兜底不影响，但跨省前缀变体需主 agent 保证竞对名规范。
"""
from __future__ import annotations

import re

from src.collector.competitor import classify_band
from src.collector.judgment import LAYER_ATTRIBUTION, RECOMMEND
from src.collector.tier import get_brand

_SEP = re.compile(r"[·•・∙．]")
_PAREN = re.compile(r"[（(].*?[)）]")


def _normalize_competitors(competitors: list, city: str) -> list[dict]:
    """竞对 → 结构化 {name, band}（字符串升级 + band 缺则 get_brand 分类，表外归 None）。

    归一化收敛在计算内部（spec ⑫ sealed 单一来源）：seal 与报告读同一口径，
    避免"seal 时字符串竞对进 unknown、报告时归一化分 band"两边不一致。
    """
    out = []
    for c in competitors:
        if isinstance(c, str):
            c = {"name": c}
        else:
            c = dict(c)
        c.setdefault("name", "")
        if not c["name"]:
            continue
        if c.get("band") is None:
            c["band"] = classify_band(get_brand(c["name"], city=city))
        out.append(c)
    return out


def normalize_hotel(name: str, city: str | None = None) -> str:
    """匹配用归一化：去间隔号/括号内容/城市前缀（保留"仓山中庚喜来登"这类带区前缀的变体）。"""
    s = _SEP.sub("", name or "").strip()
    s = _PAREN.sub("", s)
    if city:
        c = city.rstrip("市")
        if s.startswith(c):
            s = s[len(c):]
    # 兼容历史数据：无 city 传参时剥福州/福建（福州案例，跨地区由 city 参数控制）
    if s.startswith("福州"):
        s = s[2:]
    elif s.startswith("福建"):
        s = s[2:]
    return s.strip()


def competitor_in_hotels(entry: str, competitor: str, city: str | None = None) -> bool:
    """竞对是否在名单条目里：归一化后子串匹配。空核心名不匹配。"""
    nc = normalize_hotel(competitor, city)
    if not nc:
        return False
    return nc in normalize_hotel(entry, city)


# 场景(persona，与 question_templates.yaml persona 字段一致) → 命中题 question_id 前缀
# （归因题 id = attr_{场景}，同构；键必须匹配模板 persona，build_questions 按 persona 查 scenario_competitors）
_SCENARIO_PREFIX = {
    "商务差旅": "hit_business",
    "亲子家庭": "hit_family",
    "情侣度假": "hit_couple",
    "朋友结伴": "hit_friends",
    "单人出行": "hit_solo",
}


def compute_scenario_competitors(
    measurement: dict,
    competitors: list,
    city: str,
) -> dict:
    """场景匹配竞对（P1-②，2026-09-10）：每场景从**最终确认竞对**里选头号对手。

    只遍历 positioning.competitors（主=国际五星同档/次=本地高端同档，已确认清单），
    **表外/未确认酒店不参与**——新对手走覆盖度检查 → write_competitor 补确认 → 下一轮才进匹配。
    共现 = 甲方与竞对在同一题 hotels_recommended 都被推荐（AI 同场景共现）。
    返回 {"场景": 竞对名}（共现最高者），无确认竞对 → 空 dict。
    """
    client_brand = measurement.get("brand") or ""
    comps = _normalize_competitors(competitors, city)
    pinned = [c for c in comps if c.get("band") in ("main", "secondary")]
    if not pinned or not client_brand:
        return {}

    def _client_and_comp_in(hotels: list[str], comp_name: str) -> bool:
        return (any(competitor_in_hotels(e, client_brand, city) for e in hotels)
                and any(competitor_in_hotels(e, comp_name, city) for e in hotels))

    out: dict[str, str] = {}
    for scenario, prefix in _SCENARIO_PREFIX.items():
        best_name, best_count = None, -1
        for c in pinned:
            count = sum(
                1
                for info in measurement.get("platforms", {}).values()
                for j in info.get("judgments", [])
                if (j.get("question_id") or "").startswith(prefix)
                and _client_and_comp_in(j.get("hotels_recommended") or [], c["name"])
            )
            if count > best_count:
                best_name, best_count = c["name"], count
        if best_name is not None and best_count > 0:
            out[scenario] = best_name
    return out


def pinned_competitor_pushed(hotels: list[str], competitors: list, city: str) -> bool:
    """推荐名单里是否推了钉住的主/次竞对（真劣势锚定，2026-09-10）。

    真劣势 = 甲方 absent 且甲方被**钉住的竞对**（主=国际五星同档/次=本地同档）挤掉；
    仅推非钉住高端酒店（如聚春园/万达嘉华）≠ 真劣势（非甲方认定的竞对）→ 结构性。
    复用 competitor_in_hotels 归一化子串匹配（全名防"喜来登"误配"福朋喜来登"）。
    竞对空/无主次 band → False（无法锚定真劣势，防静默高估）。
    """
    comps = _normalize_competitors(competitors, city)
    main_names, secondary_names, _ = _buckets(comps)
    pinned = main_names + secondary_names
    if not pinned:
        return False
    return any(
        competitor_in_hotels(e, n, city)
        for e in hotels for n in pinned
    )


def _valid_judgments(info: dict) -> list[dict]:
    """有效分母（与 compute_platform_rate 同口径）：命中层 + has_hotel + 已判定 + 非 error。"""
    return [
        j for j in info.get("judgments", [])
        if j.get("layer") != LAYER_ATTRIBUTION
        and j.get("has_hotel_recommendations")
        and j.get("recommendation") is not None
        and j.get("reason") != "error"
    ]


def _buckets(competitors: list[dict]) -> tuple[list[str], list[str], list[str]]:
    """竞对按 band 分桶：main / secondary / unclassified（band 缺或表外）。空名跳过。"""
    main, secondary, unknown = [], [], []
    for c in competitors:
        name = (c.get("name") if isinstance(c, dict) else c) or ""
        if not name:
            continue
        band = c.get("band") if isinstance(c, dict) else None
        if band == "main":
            main.append(name)
        elif band == "secondary":
            secondary.append(name)
        else:
            unknown.append(name)
    return main, secondary, unknown


def compute_competitor_visibility(
    measurement: dict,
    competitors: list,
    city: str,
) -> dict:
    """三张表 + 主/次相对可见度 + 四象限（确定性聚合）。

    competitors = [{name, band, ...}] 或 [str]；band 缺 → 归 unclassified（不参与平均）。
    """
    platforms = measurement.get("platforms", {})
    client_overall = measurement.get("overall", {}).get("overall_hit_rate", 0.0)
    effective = measurement.get("effective_visibility")
    client_brand = measurement.get("brand") or ""
    competitors = _normalize_competitors(competitors, city)
    main_names, secondary_names, unknown = _buckets(competitors)

    def _is_client_entry(entry: str) -> bool:
        # 甲方自身的推荐条目不算任何竞对（防竞对名含/误录甲方品牌时虚增竞对率——对抗审查 Medium#3）
        return bool(client_brand) and competitor_in_hotels(entry, client_brand, city)

    # 表① 平台×竞对命中率
    per_platform: dict[str, dict] = {}
    for pl, info in platforms.items():
        valid = _valid_judgments(info)
        denom = len(valid)
        client_rate = info.get("platform_rate", {}).get("hit_rate", 0.0)
        row = {"valid": denom, "client_rate": client_rate, "main": [], "secondary": [], "unclassified": []}
        for name in main_names + secondary_names + unknown:
            # 被推荐率 = 出现题数/有效题数（按题计，同一题名单重复出现只算 1 次，甲方自身不计）
            count = sum(
                1 for j in valid
                if any(not _is_client_entry(e) and competitor_in_hotels(e, name, city) for e in j.get("hotels_recommended") or [])
            )
            item = {"name": name, "count": count, "rate": round(count / denom, 4) if denom else 0.0}
            if name in main_names:
                row["main"].append(item)
            elif name in secondary_names:
                row["secondary"].append(item)
            else:
                row["unclassified"].append(item)
        row["main_avg_rate"] = round(sum(x["rate"] for x in row["main"]) / len(row["main"]), 4) if row["main"] else 0.0
        row["secondary_avg_rate"] = round(sum(x["rate"] for x in row["secondary"]) / len(row["secondary"]), 4) if row["secondary"] else 0.0
        per_platform[pl] = row

    # 整体：甲方 = 四平台算术平均（spec 决策8）；竞对整体 = 该竞对各平台命中率平均 → 竞对组平均。
    # 分母对称：不跳过 valid==0 平台（其命中率=0.0，与甲方 compute_overall 对 valid==0 平台
    # 计入 0.0 的口径一致，防相对可见度系统性偏低——对抗审查 High#1）。
    def _band_overall(names: list[str]) -> dict:
        members = []
        for name in names:
            rates = []
            platform_rates = {}
            for pl, row in per_platform.items():
                bucket = _bucket_of(row, name)
                if bucket is None:
                    continue
                rate = next(x["rate"] for x in row[bucket] if x["name"] == name)
                rates.append(rate)
                platform_rates[pl] = rate
            members.append({
                "name": name,
                "overall_rate": round(sum(rates) / len(rates), 4) if rates else 0.0,
                "platform_rates": platform_rates,
            })
        if not names:
            return {"members": [], "avg_rate": 0.0, "relative_visibility": None, "status": "no_competitors"}
        avg = round(sum(m["overall_rate"] for m in members) / len(members), 4) if members else 0.0
        rel = round(client_overall / avg, 4) if avg > 0 else None
        return {
            "members": members,
            "avg_rate": avg,
            "relative_visibility": rel,
            "status": "ok" if avg > 0 else "platform_not_in_tier",
        }

    # 表③ 差距汇总 + 相对可见度
    overall = {
        "client_hit_rate": client_overall,
        "main": _band_overall(main_names),
        "secondary": _band_overall(secondary_names),
        "unclassified": unknown,
    }

    # 四象限诊断（spec 3.3）：有效可见度（绝对健康度）× 主相对可见度（竞争位置）
    rel_main = overall["main"]["relative_visibility"]
    absolute_high = effective is not None and effective >= 0.5
    relative_high = rel_main is not None and rel_main >= 1.0
    if absolute_high and relative_high:
        label = "强且被认可"
    elif not absolute_high and relative_high:
        label = "平台不推该档（铺信源）"
    elif absolute_high and not relative_high:
        label = "真劣势（对标竞对内容）"
    else:
        label = "双问题（内容不足+竞对抢推）"
    quadrant = {
        "effective_visibility": effective,
        "absolute_high": absolute_high,
        "relative_high": relative_high,
        "label": label,
    }

    # 表② 同题真劣势/优势定位（逐题：甲方 recommend × 各竞对在名单）
    question_detail = []
    for pl, info in platforms.items():
        for j in _valid_judgments(info):
            hotels = [e for e in (j.get("hotels_recommended") or []) if not _is_client_entry(e)]
            main_in = [n for n in main_names if any(competitor_in_hotels(e, n, city) for e in hotels)]
            secondary_in = [n for n in secondary_names if any(competitor_in_hotels(e, n, city) for e in hotels)]
            question_detail.append({
                "platform": pl,
                "question_id": j.get("question_id"),
                "question": j.get("question", ""),
                "client_recommend": j.get("recommendation") == RECOMMEND,
                "main_in": main_in,
                "secondary_in": secondary_in,
            })

    return {
        "bands": {name: ("main" if name in main_names else "secondary" if name in secondary_names else None)
                  for name in main_names + secondary_names + unknown},
        "platforms": per_platform,
        "overall": overall,
        "quadrant": quadrant,
        "question_detail": question_detail,
    }


def _bucket_of(platform_row: dict, name: str) -> str | None:
    for b in ("main", "secondary", "unclassified"):
        if any(x["name"] == name for x in platform_row[b]):
            return b
    return None
