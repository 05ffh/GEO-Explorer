"""归因树聚合（spec ⑪ P1 归因层 ①，系统确定性合成）。

把已有测量结果合成"为什么 + 怎么办"三侧归因树——读 sealed measurement 的派生字段：
- 供给侧（内容/信源）：platform_baseline 里"铺信源信号"平台（platform_sparse / platform_tier_mismatch /
  structural → 平台少列/不推甲方档位）+ content_assets（AI 现有可引用素材盘点）
- 需求侧（口碑）：sentiment 门店/品牌负面率 → 风险等级
- 竞争侧（竞对压力）：competitor_visibility 相对可见度 + 四象限 + client_content_gap 平台（推竞对不推甲方）

主方向判定（确定性优先级）：有铺信源信号平台 → 铺信源；否则 client_content_gap 平台 → 对标竞对；
否则相对可见度 < 1 → 对标竞对；否则负面率 risk=high → 治舆情；否则维持巩固。
归因结论是合成层（归因=假设，复测确认因果），不 seal 进测量版本，报告层 on-read 计算。

# ponytail: 负面率风险阈值（10%/25%）是经验值，多品牌实测后可调；对比题劣势维度（归因题采集后）在 ② 补入竞争侧细节。
"""
from __future__ import annotations

from .sentiment import combine_negative_rate

DEPLOY_SIGNAL_READINGS = {"platform_sparse", "platform_tier_mismatch", "structural"}
GAP_SIGNAL_READINGS = {"client_content_gap"}

NEGATIVE_RISK_LOW = 0.10
NEGATIVE_RISK_HIGH = 0.25


def _risk_level(rate: float | None) -> str | None:
    if rate is None:
        return None
    if rate >= NEGATIVE_RISK_HIGH:
        return "high"
    if rate >= NEGATIVE_RISK_LOW:
        return "medium"
    return "low"


_NEGATIVE_VERDICT = {
    "low": "口碑良好（负面率低），非主要短板",
    "medium": "口碑折损中等（负面率中等）→ 治舆情（次要）",
    "high": "口碑折损高（负面率高）→ 治舆情（主要）",
    None: "负面率数据不足",
}


def compute_attribution_tree(measurement: dict, sentiment: dict | None = None) -> dict:
    """归因树三侧 + 综合主方向（确定性，读 sealed 测量 + 可选 sentiment）。"""
    pb = measurement.get("platform_baseline", {}) or {}
    cv = measurement.get("competitor_visibility", {}) or {}
    main_band = (cv.get("overall") or {}).get("main") or {}
    rel = main_band.get("relative_visibility")

    deploy = [pl for pl, b in pb.items() if b.get("reading") in DEPLOY_SIGNAL_READINGS]
    gap = [pl for pl, b in pb.items() if b.get("reading") in GAP_SIGNAL_READINGS]

    store_s, brand_s = {}, {}
    if sentiment:
        store_s = sentiment.get("store_level", {}) or {}
        brand_s = sentiment.get("brand_level", {}) or {}
    store_rate, brand_rate = store_s.get("rate"), brand_s.get("rate")
    combined = measurement.get("negative_rate_combined")
    if combined is None and store_rate is not None:
        # 单档（无品牌级）→ combine 直接返回门店级；品牌级在则按 8:2。
        combined = combine_negative_rate(store_rate, brand_rate)
    level = _risk_level(combined)

    assets = measurement.get("content_assets", []) or []

    # 供给侧
    supply = {
        "deploy_signal_platforms": deploy,
        "content_asset_count": len(assets),
        "content_assets_top": assets[:10],
        "verdict": "铺信源" if deploy else "内容/信源充分",
        "evidence": (
            f"平台少列/不推甲方档位：{'、'.join(deploy)}；AI 现有可引用内容 {len(assets)} 条"
            if deploy else f"无铺信源信号平台；AI 现有可引用内容 {len(assets)} 条"
        ),
    }

    # 需求侧
    demand = {
        "store_rate": store_rate,
        "brand_rate": brand_rate,
        "combined": combined,
        "risk_level": level,
        "verdict": _NEGATIVE_VERDICT.get(level, "负面率数据不足"),
        "evidence": f"门店 {store_rate or 0:.1%} / 品牌 {brand_rate or 0:.1%}（合成 {combined:.1%}）" if combined is not None
        else f"门店 {store_rate or 0:.1%} / 品牌 {brand_rate or 0:.1%}（合成 —）",
    }

    # 竞争侧
    comp_verdict = "甲方领先国际五星，非竞对压力"
    if gap:
        comp_verdict = f"平台 {'、'.join(gap)} 推竞对不推甲方 → 对标竞对补差异化内容"
    elif rel is not None and rel < 1.0:
        comp_verdict = f"甲方相对可见度 {rel} < 1，落后于竞对平均 → 对标竞对"
    # 归因题劣势维度（P1-② 提取，接地分类）：真劣势 vs 甲方有但 AI 未引用
    from .attribution_extract import aggregate_attribution
    attr_dims = aggregate_attribution(measurement)
    true_dims = [d for d, v in attr_dims.items() if v["true_disadvantage"] > 0]
    unreferenced_dims = [d for d, v in attr_dims.items() if v["client_has_unreferenced"] > 0]
    if true_dims:
        # 追加而非覆盖：整体领先（rel>1）与局部维度真劣势可并存（对抗审查 2026-09-10）
        comp_verdict = f"{comp_verdict}；对比题显示甲方在 {'、'.join(true_dims)} 维度真劣势 → 对标竞对补差异"
    competition = {
        "relative_visibility": rel,
        "quadrant_label": (cv.get("quadrant") or {}).get("label"),
        "client_gap_platforms": gap,
        "main_band_avg_rate": main_band.get("avg_rate"),
        "disadvantage_dims": attr_dims,              # 归因题劣势/优势维度（接地分类）
        "true_disadvantage_dims": true_dims,
        "client_has_unreferenced_dims": unreferenced_dims,
        "verdict": comp_verdict,
        "evidence": f"相对可见度 {rel if rel is not None else '—'}，四象限：{(cv.get('quadrant') or {}).get('label') or '—'}",
    }

    # 综合主方向（确定性优先级）
    if deploy:
        primary = {"direction": "铺信源（供给侧）",
                   "reason": f"平台 {'、'.join(deploy)} 少列/不推甲方档位 → 去对应平台信源铺内容"}
    elif gap:
        primary = {"direction": "对标竞对（竞争侧）",
                   "reason": f"平台 {'、'.join(gap)} 推竞对不推甲方 → 对标竞对补差异化内容"}
    elif rel is not None and rel < 1.0:
        primary = {"direction": "对标竞对（竞争侧）",
                   "reason": f"甲方相对可见度 {rel} < 1，落后于竞对平均"}
    elif level == "high":
        primary = {"direction": "治舆情（需求侧）",
                   "reason": f"负面率合成 {combined:.1%} 高 → 处理口碑"}
    else:
        primary = {"direction": "维持巩固",
                   "reason": "无显著短板，甲方在竞争带内位置良好"}

    secondary = []
    if level in ("medium", "high") and primary["direction"] != "治舆情（需求侧）":
        secondary.append(f"治舆情（负面率合成 {combined:.1%}）")
    if gap and primary["direction"].startswith("铺信源"):
        secondary.append(f"对标竞对（平台 {'、'.join(gap)} 推竞对不推甲方）")

    return {
        "supply_side": supply,
        "demand_side": demand,
        "competition_side": competition,
        "conclusion": {
            "primary": primary,
            "secondary": secondary,
            "summary": f"主方向：{primary['direction']}。{primary['reason']}"
                       + (f"；次：{'、'.join(secondary)}。" if secondary else "。"),
        },
    }
