"""P0-B 平台信源调性测试：基线计算 + 确定性解读分类 + close_measurement 收口。"""

from src.collector.hit_rate import close_measurement
from src.collector.platform_baseline import (
    apply_review, compute_platform_baseline, _high_end_ratio_from_judgments, _read_platform,
)


def _judgment(qid, hotels, dist, layer="hit", reason="agent_finalized", reco="default"):
    if reco == "default":
        reco = "recommend" if hotels else "absent"
    return {
        "question_id": qid, "layer": layer, "reason": reason,
        "recommendation": reco,
        "has_hotel_recommendations": bool(hotels),
        "hotels_recommended": hotels,
        "answer_tier_distribution": dist,
    }


def _mk(pl, hit_rate, judgments, band_avg):
    m = {
        "competitor_visibility": {"platforms": {pl: {"main_avg_rate": band_avg}}},
        "platforms": {pl: {"judgments": judgments, "platform_rate": {"hit_rate": hit_rate}}},
    }
    return m


def test_avg_hotels_listed_includes_no_hotel_questions():
    # 只答区域（hotels=[]）计入分母为 0，反映"平台少列"；未判定题（reco=None）不计
    judgments = [
        _judgment("q1", ["a", "b", "c"], {"高端": 3, "中端": 1}),
        _judgment("q2", ["a"], {"高端": 1}),
        _judgment("q3", [], {}),                              # 只答区域 → 0
        _judgment("q4", ["x", "y"], {"中端": 2}, reco=None),   # 未判定 → 不计
    ]
    m = _mk("deepseek", 0.6, judgments, 0.5)
    b = compute_platform_baseline(m, "高端")
    assert b["deepseek"]["avg_hotels_listed"] == round((3 + 1 + 0) / 3, 2)  # 未判定题排除
    assert b["deepseek"]["hit_rate"] == 0.6
    assert b["deepseek"]["main_band_avg_rate"] == 0.5
    assert b["deepseek"]["reading"] == "normal"  # hit 0.6 ≥ 0.5


def test_high_end_ratio_missing_tier_counts_zero():
    """对抗审查 HIGH 修复：缺失档按 0 计——甲方档只出现在少数题时不高估。
    旧 aggregate_platform_profile 只对出现该档的题求均值 → 甲方档=1.0（虚高），
    新算法按全部档位计数 → 真实占比 10%。"""
    judgments = [_judgment(f"q{i}", ["h"] * 4, {"高端": 4} if i == 0 else {"中端": 4}) for i in range(10)]
    assert _high_end_ratio_from_judgments(judgments, "高端") == round(4 / 40, 4)  # 0.1，非 1.0


def test_high_end_ratio_uses_client_tier_and_above():
    judgments = [_judgment("q1", ["a"] * 10, {"经济": 2, "中端": 2, "中高端": 2, "高端": 2, "豪华": 2})]
    assert _high_end_ratio_from_judgments(judgments, "中高端") == round(6 / 10, 4)  # 中高端+高端+豪华
    assert _high_end_ratio_from_judgments(judgments, "高端") == round(4 / 10, 4)
    assert _high_end_ratio_from_judgments(judgments, "表外档") is None
    assert _high_end_ratio_from_judgments([], "高端") == 0.0


def test_reading_classification_with_none_states():
    assert _read_platform(0.6, 5.0, 0.5, 0.4) == "normal"                    # 正常
    assert _read_platform(0.1, 2.0, 0.5, 0.4) == "platform_sparse"          # 平台简短（先于数据不足）
    assert _read_platform(0.1, 5.0, None, 0.4) == "tier_unknown"            # 甲方档位未知
    assert _read_platform(0.1, 5.0, 0.5, None) == "no_band_data"            # 无竞对数据
    assert _read_platform(0.1, 5.0, 0.2, 0.4) == "platform_tier_mismatch"   # 平台不推甲方档位
    assert _read_platform(0.0, 5.0, 0.5, 0.4) == "client_content_gap"       # 竞对被推甲方 0 → 甲方内容不足
    assert _read_platform(0.0, 5.0, 0.5, 0.2) == "structural"               # 竞对也低 → 结构性


def test_no_competitor_visibility_is_no_band_data_not_structural():
    # 无竞对（competitor_visibility 缺失）→ band_avg=None → no_band_data，不误判 structural
    m = _mk("deepseek", 0.0, [_judgment("q1", ["a", "b", "c", "d", "e"], {"高端": 5})], None)
    m.pop("competitor_visibility")  # 模拟无竞对
    b = compute_platform_baseline(m, "高端")
    assert b["deepseek"]["reading"] == "no_band_data"
    assert b["deepseek"]["main_band_avg_rate"] is None


def test_close_measurement_includes_and_clears_platform_baseline():
    m = {
        "brand": "香格里拉", "city": "福州",
        "platforms": {"deepseek": {"judgments": [_judgment("q1", ["福州香格里拉大酒店"], {"高端": 2}, reco="recommend")]}},
    }
    senti = {"store_level": {"rate": 0.16, "status": "confirmed"},
             "brand_level": {"rate": 0.14, "status": "confirmed"}}
    competitors = [{"name": "福州世茂洲际酒店", "band": "main"}]

    close_measurement(m, competitors=competitors, sentiment=senti, city="福州", client_tier="高端")
    assert "platform_baseline" in m
    assert m["platform_baseline"]["deepseek"]["reading"] == "normal"

    # 重关不传 client_tier → platform_baseline 移除，不残留旧值
    close_measurement(m, competitors=competitors, sentiment=senti, city="福州", client_tier=None)
    assert "platform_baseline" not in m


def test_close_measurement_unknown_tier_hotels_alert():
    # 表外告警：推荐名单里 brand_domains 查不到档位的酒店显式记录（sealed），无表外则移除
    m = {"brand": "香格里拉", "city": "福州",
         "platforms": {"deepseek": {"judgments": [
             _judgment("q1", ["福州香格里拉大酒店", "福州某新开高端酒店"], {"高端": 2})]}}}
    close_measurement(m, city="福州", client_tier="高端")
    assert "福州某新开高端酒店" in m["unknown_tier_hotels"]     # 表外酒店被记录
    assert "福州香格里拉大酒店" not in m["unknown_tier_hotels"]  # 表内（香格里拉）不记

    m2 = {"brand": "香格里拉", "city": "福州",
          "platforms": {"deepseek": {"judgments": [
              _judgment("q1", ["福州香格里拉大酒店"], {"高端": 2})]}}}
    close_measurement(m2, city="福州", client_tier="高端")
    assert "unknown_tier_hotels" not in m2                       # 无表外 → 移除，不残留


def test_close_measurement_pinned_competitor_anchors_true_disadvantage():
    # 真劣势锚定钉住竞对（2026-09-10）：absent + 推荐名单出现钉住主竞对 → 真劣势；
    # 非钉住高端（聚春园）→ 结构性（非甲方认定的竞对）
    m = {"brand": "香格里拉", "city": "福州",
         "platforms": {"deepseek": {"judgments": [
             _judgment("q1", ["福州世茂洲际酒店"], {"高端": 1}, reco="absent"),
             _judgment("q2", ["福州聚春园大酒店"], {"高端": 1}, reco="absent"),
         ]}}}
    comps = [{"name": "福州世茂洲际酒店", "band": "main"},
             {"name": "福州泰禾凯宾斯基酒店", "band": "main"},
             {"name": "福州中庚喜来登", "band": "main"},
             {"name": "福州西湖大酒店", "band": "secondary"},
             {"name": "福建外贸中心悦华酒店", "band": "secondary"}]
    close_measurement(m, competitors=comps, city="福州", client_tier="高端")
    js = {j["question_id"]: j for j in m["platforms"]["deepseek"]["judgments"]}
    assert js["q1"]["same_tier_pushed"] is True     # 推了钉住主竞对 → 真劣势
    assert js["q2"]["same_tier_pushed"] is False    # 非钉住高端 → 结构性
    assert m["miss_structure"]["true_disadvantage"] == 1
    assert m["miss_structure"]["structural"] == 1


def test_apply_review_revise_and_confirm():
    # 系统先验 reading → 主 agent 改判/确认 + 审计记录
    m = _mk("wenxin", 0.0, [_judgment("q1", [], {})], None)
    baseline = compute_platform_baseline(m, "高端")
    assert baseline["wenxin"]["reading"] == "platform_sparse"  # avg 0 < 3

    # 主 agent 核对语境后改判：文心实际列了高档但格式不列清单
    apply_review(baseline, {"wenxin": {"reading": "client_content_gap", "reason": "实际列高档酒店但格式未列清单"}})
    rv = baseline["wenxin"]["review"]
    assert rv["status"] == "revised"
    assert rv["system_reading"] == "platform_sparse"
    assert rv["reviewed_reading"] == "client_content_gap"
    assert "reason" in rv and rv["reviewer"] == "main_agent"
    assert baseline["wenxin"]["reading"] == "client_content_gap"

    # 确认（reading 与系统一致）→ status=confirmed，reading 不变
    apply_review(baseline, {"wenxin": {"reading": "client_content_gap", "reason": "复核一致"}})
    assert baseline["wenxin"]["review"]["status"] == "confirmed"


def test_apply_review_invalid_reading_rejected():
    m = _mk("deepseek", 0.0, [_judgment("q1", ["a"] * 5, {"高端": 5})], None)
    baseline = compute_platform_baseline(m, "高端")
    import pytest
    with pytest.raises(ValueError):
        apply_review(baseline, {"deepseek": {"reading": "瞎编的", "reason": "x"}})
    assert "review" not in baseline["deepseek"]  # 未写入


def test_apply_review_revised_requires_reason_and_unknown_platform_rejected():
    m = _mk("deepseek", 0.0, [_judgment("q1", ["a"] * 5, {"高端": 5})], None)
    baseline = compute_platform_baseline(m, "高端")
    import pytest
    # 改判必须留 reason
    with pytest.raises(ValueError):
        apply_review(baseline, {"deepseek": {"reading": "client_content_gap", "reason": "  "}})
    # 未知平台报错（不静默跳过）
    with pytest.raises(ValueError):
        apply_review(baseline, {"not_a_platform": {"reading": "normal", "reason": "x"}})


def test_close_measurement_preserves_review_with_stale_mark():
    """rejudge 重算 platform_baseline 后，复核记录保留并标 stale（不静默清掉人审痕迹）。"""
    m = {
        "brand": "香格里拉", "city": "福州",
        "platforms": {"deepseek": {"judgments": [_judgment("q1", ["福州香格里拉大酒店"], {"高端": 2}, reco="recommend")]}},
    }
    senti = {"store_level": {"rate": 0.16, "status": "confirmed"},
             "brand_level": {"rate": 0.14, "status": "confirmed"}}
    competitors = [{"name": "福州世茂洲际酒店", "band": "main"}]

    close_measurement(m, competitors=competitors, sentiment=senti, city="福州", client_tier="高端")
    # 主 agent 复核：改判
    apply_review(m["platform_baseline"], {"deepseek": {"reading": "client_content_gap", "reason": "实际列了高档但未列清单"}})
    assert m["platform_baseline"]["deepseek"]["review"]["status"] == "revised"
    # rejudge：close_measurement 重算 → reading 回到系统值，但 review 保留 + stale
    close_measurement(m, competitors=competitors, sentiment=senti, city="福州", client_tier="高端")
    rv = m["platform_baseline"]["deepseek"]["review"]
    assert rv is not None and rv["status"] == "revised"          # 人审记录保留
    assert rv["stale"] is True                                    # 系统重判后 reading 与复核值不一致 → stale
    assert m["platform_baseline"]["deepseek"]["reading"] == "normal"  # 系统值
