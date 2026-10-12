"""P0-A 竞对聚合测试：band 分类 + 匹配归一化 + 相对可见度聚合 + 除零边界。"""

import pytest

from src.collector.competitor import classify_band, COMPETITOR_BAND_MAIN, COMPETITOR_BAND_SECONDARY
from src.collector.competitor_visibility import (
    compute_competitor_visibility, compute_scenario_competitors,
    competitor_in_hotels, normalize_hotel, pinned_competitor_pushed,
)
from src.collector.tier import get_brand

PINNED = [
    {"name": "福州世茂洲际酒店", "band": "main"},
    {"name": "福州泰禾凯宾斯基酒店", "band": "main"},
    {"name": "福州中庚喜来登", "band": "main"},
    {"name": "福州西湖大酒店", "band": "secondary"},
    {"name": "福建外贸中心悦华酒店", "band": "secondary"},
]


# ── band 分类 ──

def test_classify_band_international_five_star():
    assert classify_band(get_brand("福州世茂洲际酒店", city="福州")) == COMPETITOR_BAND_MAIN
    assert classify_band(get_brand("福州泰禾凯宾斯基酒店", city="福州")) == COMPETITOR_BAND_MAIN
    assert classify_band(get_brand("福州中庚喜来登", city="福州")) == COMPETITOR_BAND_MAIN


def test_classify_band_local_high_end():
    assert classify_band(get_brand("福州西湖大酒店", city="福州")) == COMPETITOR_BAND_SECONDARY
    assert classify_band(get_brand("福建外贸中心悦华酒店", city="福州")) == COMPETITOR_BAND_SECONDARY


def test_classify_band_none_for_unknown_or_low_tier():
    assert classify_band(None) is None
    assert classify_band(get_brand("福州如家", city="福州")) is None  # 经济档非甲方同档


# ── 归一化 + 匹配 ──

def test_normalize_hotel_strips_prefix_paren_sep():
    assert normalize_hotel("福州世茂洲际酒店", "福州") == "世茂洲际酒店"
    assert normalize_hotel("福州西湖大酒店（近三坊七巷店）", "福州") == "西湖大酒店"
    assert normalize_hotel("福州西湖大酒店(近三坊七巷店)", "福州") == "西湖大酒店"
    assert normalize_hotel("福建外贸中心悦华酒店", "福州") == "外贸中心悦华酒店"


def test_match_variants():
    assert competitor_in_hotels("仓山中庚喜来登", "福州中庚喜来登", "福州")
    assert competitor_in_hotels("泰禾凯宾斯基酒店", "福州泰禾凯宾斯基酒店", "福州")
    assert competitor_in_hotels("福建外贸中心悦华酒店（三坊七巷店）", "福建外贸中心悦华酒店", "福州")


def test_match_no_false_positive_four_points():
    # "喜来登"是"福朋喜来登"子串，但竞对核心名"中庚喜来登"不应误配福朋喜来登
    assert not competitor_in_hotels("福州晋安福朋喜来登酒店", "福州中庚喜来登", "福州")


# ── 聚合（合成 measurement，已知值）──

def _j(qid, recommendation, hotels, has_hotel=True, layer="hit", error=False):
    return {
        "question_id": qid, "layer": layer, "recommendation": recommendation,
        "has_hotel_recommendations": has_hotel,
        "reason": "error" if error else "agent_finalized",
        "hotels_recommended": hotels, "question": qid,
    }


def _mk(judgments, hit_rate, overall, effective=0.5):
    return {
        "overall": {"overall_hit_rate": overall},
        "effective_visibility": effective,
        "platforms": {"deepseek": {"platform_rate": {"hit_rate": hit_rate}, "judgments": judgments}},
    }


COMPETITORS = [
    {"name": "福州世茂洲际酒店", "band": "main"},
    {"name": "福州泰禾凯宾斯基酒店", "band": "main"},
    {"name": "福州西湖大酒店", "band": "secondary"},
]


def test_compute_visibility_known_values():
    m = _mk(
        [
            _j("q1", "recommend", ["福州世茂洲际酒店", "福州香格里拉大酒店"]),
            _j("q2", "absent", ["福州泰禾凯宾斯基酒店", "福州西湖大酒店"]),
            _j("q3", "absent", ["福州西湖大酒店"]),
            _j("q4", "recommend", ["福州香格里拉大酒店"], error=True),  # error 排除
        ],
        hit_rate=0.33, overall=0.33,
    )
    r = compute_competitor_visibility(m, COMPETITORS, "福州")
    ds = r["platforms"]["deepseek"]
    assert ds["valid"] == 3  # error 题排除出分母
    # 世茂洲际 1/3、凯宾斯基 1/3、西湖大酒店 2/3
    assert {x["name"]: x["count"] for x in ds["main"]} == {"福州世茂洲际酒店": 1, "福州泰禾凯宾斯基酒店": 1}
    assert {x["name"]: x["count"] for x in ds["secondary"]} == {"福州西湖大酒店": 2}
    assert ds["main_avg_rate"] == round(1 / 3, 4)
    # 整体主相对可见度 = 甲方 0.33 ÷ 主平均 (1/3)
    assert r["overall"]["main"]["avg_rate"] == round(1 / 3, 4)
    assert r["overall"]["main"]["relative_visibility"] == pytest.approx(0.99, abs=0.01)
    assert r["overall"]["main"]["status"] == "ok"
    # 四象限：有效 0.5≥0.5（绝对高）× 相对≈0.99<1（相对低）→ 真劣势
    assert r["quadrant"]["absolute_high"] is True
    assert r["quadrant"]["relative_high"] is False
    assert r["quadrant"]["label"] == "真劣势（对标竞对内容）"


def test_relative_div_by_zero_structural():
    # 竞对平均 = 0 → 结构性标记，非 NaN
    m = _mk(
        [
            _j("q1", "recommend", ["福州香格里拉大酒店"]),
            _j("q2", "recommend", ["福州香格里拉大酒店"]),
        ],
        hit_rate=1.0, overall=1.0,
    )
    r = compute_competitor_visibility(m, COMPETITORS, "福州")
    assert r["overall"]["main"]["avg_rate"] == 0.0
    assert r["overall"]["main"]["relative_visibility"] is None
    assert r["overall"]["main"]["status"] == "platform_not_in_tier"


def test_client_own_entry_not_counted_as_competitor():
    # 甲方自身（香格里拉）的推荐条目不计入任何竞对：即使竞对名归一化后是"香格里拉"也不虚增
    m = _mk(
        [_j("q1", "recommend", ["福州香格里拉大酒店", "福州世茂洲际酒店"])],
        hit_rate=0.5, overall=0.5,
    )
    m["brand"] = "香格里拉"
    r = compute_competitor_visibility(m, [{"name": "福州香格里拉", "band": "main"}], "福州")
    assert r["platforms"]["deepseek"]["main"][0]["count"] == 0


def test_no_competitors_status():
    # 有竞对但 band 全 None（表外）→ 主竞争带 status=no_competitors，与 platform_not_in_tier 区分
    m = _mk([_j("q1", "recommend", ["福州世茂洲际酒店"])], hit_rate=1.0, overall=1.0)
    r = compute_competitor_visibility(m, [{"name": "某表外酒店", "band": None}], "福州")
    assert r["overall"]["main"]["status"] == "no_competitors"
    assert r["overall"]["main"]["relative_visibility"] is None


def test_valid_zero_platform_symmetric_denominator():
    # 某平台 total>0 但 valid=0（全部无酒店推荐）→ 甲方与竞对都计入该平台 0.0，相对可见度不系统性偏低
    wenxin_judgments = [_j(f"q{i}", "absent", [], has_hotel=False) for i in range(25)]
    deepseek_judgments = [
        _j("d1", "recommend", ["福州世茂洲际酒店"]),
        _j("d2", "recommend", []),
    ]
    m = {
        "overall": {"overall_hit_rate": 0.25},  # (0.5 + 0.0) / 2
        "effective_visibility": 0.5,
        "platforms": {
            "deepseek": {"platform_rate": {"hit_rate": 0.5}, "judgments": deepseek_judgments},
            "wenxin": {"platform_rate": {"hit_rate": 0.0}, "judgments": wenxin_judgments},
        },
    }
    r = compute_competitor_visibility(m, [{"name": "福州世茂洲际酒店", "band": "main"}], "福州")
    # 竞对整体 = (deepseek 0.5 + wenxin 0.0) / 2 = 0.25，与甲方 0.25 对称 → 相对 1.0
    assert r["overall"]["main"]["avg_rate"] == round(0.25, 4)
    assert r["overall"]["main"]["relative_visibility"] == pytest.approx(1.0, abs=0.01)


def test_compute_normalizes_string_competitors():
    """字符串竞对在计算内部归一化 band（spec ⑫ 单一口径）：纯字符串 → 归 main，不进 unknown。"""
    m = _mk([_j("q1", "recommend", ["福州世茂洲际酒店"])], hit_rate=1.0, overall=1.0)
    m["brand"] = "香格里拉"
    r = compute_competitor_visibility(m, ["福州世茂洲际酒店"], "福州")  # 纯字符串，无 band
    assert r["platforms"]["deepseek"]["main"][0]["name"] == "福州世茂洲际酒店"
    assert r["platforms"]["deepseek"]["main"][0]["count"] == 1
    assert r["overall"]["main"]["status"] == "ok"


def test_question_detail_marks_true_disadvantage():
    m = _mk(
        [
            _j("q1", "absent", ["福州世茂洲际酒店"]),          # 竞对在、甲方未推荐 → 真劣势
            _j("q2", "recommend", ["福州香格里拉大酒店"]),      # 甲方在
            _j("q3", "absent", []),
        ],
        hit_rate=0.33, overall=0.33,
    )
    r = compute_competitor_visibility(m, COMPETITORS, "福州")
    d1 = next(d for d in r["question_detail"] if d["question_id"] == "q1")
    assert d1["client_recommend"] is False and d1["main_in"] == ["福州世茂洲际酒店"]
    d3 = next(d for d in r["question_detail"] if d["question_id"] == "q3")
    assert d3["main_in"] == [] and d3["secondary_in"] == []


# ── 真劣势锚定（pinned_competitor_pushed，2026-09-10）──

def test_pinned_pushed_main_competitor():
    # 推荐名单出现钉住主竞对 → True（甲方被主竞对挤掉 = 真劣势）
    assert pinned_competitor_pushed(["福州全季酒店", "福州世茂洲际酒店"], PINNED, "福州") is True


def test_pinned_pushed_secondary_competitor():
    assert pinned_competitor_pushed(["福州西湖大酒店"], PINNED, "福州") is True  # 次竞对（本地同档）


def test_pinned_pushed_non_pinned_high_end_is_false():
    # 非钉住高端（聚春园/万达嘉华）→ False：不是甲方认定的竞对，推了 ≠ 真劣势（结构性）
    assert pinned_competitor_pushed(["福州聚春园大酒店", "福州万达嘉华"], PINNED, "福州") is False


def test_pinned_pushed_no_false_positive_four_points():
    # 归一化全名匹配：中庚喜来登不误配"福朋喜来登"
    assert pinned_competitor_pushed(["福州福朋喜来登（晋安）"], PINNED, "福州") is False


def test_pinned_pushed_no_pinned_competitors():
    assert pinned_competitor_pushed(["福州世茂洲际酒店"], [], "福州") is False  # 无钉住竞对 → 无法锚定


# ── 场景匹配竞对（P1-②，2026-09-10）──

def test_compute_scenario_competitors_top_rival_per_scenario():
    # 商务：世茂洲际共现 2 > 凯宾斯基 1；带娃：西湖共现 1；独自：无竞对共现 → 不出
    m = {"brand": "香格里拉", "platforms": {"deepseek": {"judgments": [
        _j("hit_business_generic", "recommend", ["福州香格里拉大酒店", "福州世茂洲际酒店"]),
        _j("hit_business_transit", "recommend", ["福州香格里拉大酒店", "福州世茂洲际酒店", "福州泰禾凯宾斯基酒店"]),
        _j("hit_family_generic", "recommend", ["福州香格里拉大酒店", "福州西湖大酒店"]),
        _j("hit_solo_generic", "recommend", ["福州香格里拉大酒店"]),
    ]}}}
    sc = compute_scenario_competitors(m, PINNED, "福州")
    assert sc["商务差旅"] == "福州世茂洲际酒店"   # 共现 2 最高
    assert sc["亲子家庭"] == "福州西湖大酒店"     # 次竞对可成为场景头号对手
    assert "单人出行" not in sc                    # 无竞对共现 → 该场景不出


def test_compute_scenario_competitors_ignores_unconfirmed_hotels():
    # 表外/未确认酒店（聚春园）不参与场景匹配——只从确认竞对（PINNED）里选
    m = {"brand": "香格里拉", "platforms": {"deepseek": {"judgments": [
        _j("hit_business_generic", "recommend", ["福州香格里拉大酒店", "福州聚春园大酒店"]),
    ]}}}
    sc = compute_scenario_competitors(m, PINNED, "福州")
    assert "商务差旅" not in sc                     # 聚春园未确认 → 商务无头号对手


def test_compute_scenario_competitors_no_competitors():
    assert compute_scenario_competitors({"brand": "香格里拉", "platforms": {}}, [], "福州") == {}
