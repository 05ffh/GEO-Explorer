"""P1 归因层 ① 归因树聚合测试：三侧已知值 + 主方向确定性优先级 + 负面率合成。"""

from src.collector.attribution_tree import compute_attribution_tree


def _m(pl_readings=None, rel=None, quad=None, neg=None, assets=None):
    """构造 measurement 骨架（只含归因树用到的字段）。"""
    return {
        "platform_baseline": {pl: {"reading": r} for pl, r in (pl_readings or {}).items()},
        "competitor_visibility": {
            "overall": {"main": {"relative_visibility": rel, "avg_rate": 0.2}},
            "quadrant": {"label": quad},
        },
        "negative_rate_combined": neg,
        "content_assets": [{"content": f"素材{i}", "count": 1} for i in range(assets or 0)],
    }


def test_supply_demand_competition_three_sides():
    m = _m(
        pl_readings={"wenxin": "platform_sparse", "doubao": "structural"},
        rel=1.8, quad="甲方领先", neg=0.15, assets=76,
    )
    t = compute_attribution_tree(m)
    # 供给侧
    assert t["supply_side"]["deploy_signal_platforms"] == ["wenxin", "doubao"]  # 按 platform_baseline 插入序
    assert t["supply_side"]["content_asset_count"] == 76
    assert t["supply_side"]["verdict"] == "铺信源"
    # 需求侧
    assert t["demand_side"]["combined"] == 0.15
    assert t["demand_side"]["risk_level"] == "medium"
    # 竞争侧（rel>=1 无 gap → 非竞对压力）
    assert t["competition_side"]["relative_visibility"] == 1.8
    assert t["competition_side"]["client_gap_platforms"] == []
    assert "非竞对压力" in t["competition_side"]["verdict"]


def test_primary_priority_deploy_signal():
    # 有铺信源信号平台 → 主方向铺信源（即使 rel>=1）
    m = _m(pl_readings={"doubao": "structural"}, rel=2.0, neg=0.05)
    c = compute_attribution_tree(m)["conclusion"]
    assert c["primary"]["direction"] == "铺信源（供给侧）"


def test_primary_priority_gap_beats_relative():
    # 无铺信源信号，有 client_content_gap → 对标竞对
    m = _m(pl_readings={"kimi": "client_content_gap"}, rel=2.0, neg=0.05)
    c = compute_attribution_tree(m)["conclusion"]
    assert c["primary"]["direction"] == "对标竞对（竞争侧）"


def test_primary_priority_relative_below_one():
    # 无信号无 gap，rel<1 → 对标竞对
    m = _m(rel=0.6, neg=0.05)
    c = compute_attribution_tree(m)["conclusion"]
    assert c["primary"]["direction"] == "对标竞对（竞争侧）"


def test_primary_priority_high_risk():
    # 无信号无 gap rel>=1，负面率 high → 治舆情
    m = _m(rel=1.2, neg=0.3)
    c = compute_attribution_tree(m)["conclusion"]
    assert c["primary"]["direction"] == "治舆情（需求侧）"


def test_primary_default_maintain():
    m = _m(rel=1.2, neg=0.05)
    c = compute_attribution_tree(m)["conclusion"]
    assert c["primary"]["direction"] == "维持巩固"
    assert c["secondary"] == []


def test_secondary_medium_risk_appended():
    # 主方向铺信源 + 负面率 medium → 次方向治舆情
    m = _m(pl_readings={"wenxin": "platform_sparse"}, rel=1.5, neg=0.15)
    c = compute_attribution_tree(m)["conclusion"]
    assert c["primary"]["direction"] == "铺信源（供给侧）"
    assert any("治舆情" in s for s in c["secondary"])


def test_secondary_gap_appended_to_deploy():
    # 主方向铺信源 + 有 gap 平台 → 次方向对标竞对
    m = _m(pl_readings={"wenxin": "platform_sparse", "kimi": "client_content_gap"}, rel=1.5, neg=0.05)
    c = compute_attribution_tree(m)["conclusion"]
    assert c["primary"]["direction"] == "铺信源（供给侧）"
    assert any("对标竞对" in s for s in c["secondary"])


def test_combined_falls_back_to_sentiment_802():
    # negative_rate_combined 缺失 → 0.8*门店 + 0.2*品牌 合成
    m = _m(rel=1.2)
    m.pop("negative_rate_combined")
    senti = {"store_level": {"rate": 0.2}, "brand_level": {"rate": 0.1}}
    t = compute_attribution_tree(m, senti)
    assert t["demand_side"]["combined"] == round(0.8 * 0.2 + 0.2 * 0.1, 4)  # 0.18 medium
    assert t["demand_side"]["risk_level"] == "medium"


def test_negative_rate_data_insufficient():
    # 无负面率 + 无 sentiment → 需求侧数据不足，不误判治舆情
    m = _m(rel=1.2)
    t = compute_attribution_tree(m)
    assert t["demand_side"]["risk_level"] is None
    assert t["conclusion"]["primary"]["direction"] == "维持巩固"


def test_competition_side_consumes_attribution_dims():
    # 归因树竞争侧消费劣势维度（P1-②）：有真劣势维度 → 结论对标竞对补差异
    m = _m(rel=1.2, neg=0.05)
    m["platforms"] = {"deepseek": {"judgments": [
        {"question_id": "attr_business", "layer": "attribution",
         "attribution_result": {"pick": "competitor",
                                "client_disadvantage_dims": [
                                    {"dim": "位置", "type": "true_disadvantage", "evidence": "世茂洲际市中心"},
                                    {"dim": "设施", "type": "client_has_unreferenced", "evidence": "香格里拉有泳池没提"}],
                                "client_advantage_dims": []}},
    ]}}
    t = compute_attribution_tree(m)
    comp = t["competition_side"]
    assert comp["true_disadvantage_dims"] == ["位置"]
    assert comp["client_has_unreferenced_dims"] == ["设施"]
    assert "真劣势" in comp["verdict"] and "位置" in comp["verdict"]
    assert comp["disadvantage_dims"]["位置"]["true_disadvantage"] == 1
