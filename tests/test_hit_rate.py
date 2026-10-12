"""命中率计算测试（A-3 新口径 2026-09-04）：二分命中率 + 子场景首推/均排 + 分母净化 + 未命中结构 + 整体 + 有效可见度。

mock judgment 按 src/collector/judgment.py schema。
"""
from src.collector.hit_rate import (
    compute_platform_rate, compute_overall, effective_visibility, finalize_measurement,
    compute_persona_rates, aggregate_platform_profile, aggregate_content_assets,
)
from src.collector.judgment import RECOMMEND, MENTION, EXCLUDE, ABSENT, LAYER_HIT


def _j(question_id, reco, scene=None, same=None, has_hotel=True, dist=None, content=None, layer=LAYER_HIT):
    return {
        "question_id": question_id,
        "layer": layer,
        "platform": "mock",
        "recommendation": reco,
        "scene": scene,
        "same_tier_pushed": same,
        "answer_tier_distribution": dist,
        "referred_content": content or [],
        "has_hotel_recommendations": has_hotel,
        "hit": None,
        "needs_agent": reco is None,
        "reason": None,
    }


def test_platform_rate_basic():
    judgments = [
        _j("q1", RECOMMEND, scene={"dim": "region", "val": "鼓楼区", "rank_in_scene": 1, "in_scene_count": 3}),
        _j("q2", RECOMMEND, scene={"dim": "region", "val": "鼓楼区", "rank_in_scene": 2, "in_scene_count": 3}),
        _j("q3", MENTION),
        _j("q4", ABSENT, same=True),   # 真劣势
    ]
    r = compute_platform_rate(judgments)
    assert r["total"] == 4
    assert r["valid"] == 4
    assert r["hit_count"] == 2
    assert r["hit_rate"] == 0.5        # 2/4（二分：只有 recommend 命中）
    assert r["first_rate"] == 0.25     # scene.rank_in_scene==1 有 1 题
    assert r["avg_rank"] == 1.5        # (1+2)/2
    assert r["miss_structure"]["true_disadvantage"] == 1
    assert r["miss_structure"]["mention"] == 1


def test_denominator_purge_no_hotel_rec():
    # 无酒店推荐（has_hotel_recommendations=false）→ 排除分母
    judgments = [
        _j("q1", RECOMMEND, scene={"dim": "region", "val": "x", "rank_in_scene": 1, "in_scene_count": 1}),
        _j("q2", ABSENT, has_hotel=False),   # AI 只答区域，无酒店推荐
    ]
    r = compute_platform_rate(judgments)
    assert r["valid"] == 1
    assert r["no_hotel_rec"] == 1
    assert r["hit_rate"] == 1.0


def test_undecided_excluded_from_denom():
    # recommendation None（待子 agent）→ 不进分母，统计 undecided
    judgments = [
        _j("q1", RECOMMEND, scene={"dim": "tier", "val": "高端", "rank_in_scene": 1, "in_scene_count": 2}),
        _j("q2", None),
    ]
    r = compute_platform_rate(judgments)
    assert r["undecided"] == 1
    assert r["valid"] == 1
    assert r["hit_rate"] == 1.0


def test_structural_vs_question_mismatch():
    # 结构性：absent + 未推甲方同档 → structural；题面错位：同情况但题目带档位词
    j1 = _j("hit_solo_generic", ABSENT, same=False)
    j2 = _j("hit_business_transit", ABSENT, same=False)
    tier_words = {"hit_business_transit"}
    r = compute_platform_rate([j1, j2], tier_word_questions=tier_words)
    assert r["miss_structure"]["structural"] == 1
    assert r["miss_structure"]["question_mismatch"] == 1
    # 不传 tier_word_questions → 题面错位并入结构性
    r2 = compute_platform_rate([j1, j2])
    assert r2["miss_structure"]["structural"] == 2
    assert r2["miss_structure"]["question_mismatch"] == 0


def test_exclude_and_avg_rank_insufficient():
    j = [
        _j("q1", EXCLUDE),
        _j("q2", RECOMMEND, scene={"dim": "tier", "val": "高端", "rank_in_scene": 1, "in_scene_count": 2}),
    ]
    r = compute_platform_rate(j)
    assert r["miss_structure"]["exclude"] == 1
    assert r["avg_rank"] == 1.0
    assert r["avg_rank_insufficient"] is True   # 只命中 1 题


def test_empty_judgments():
    r = compute_platform_rate([])
    assert r["hit_rate"] == 0.0
    assert r["avg_rank"] is None
    assert r["miss_structure"]["structural"] == 0


def test_finalize_measurement_rebuilds():
    m = {
        "platforms": {
            "deepseek": {
                "judgments": [
                    _j("q1", RECOMMEND, scene={"dim": "region", "val": "鼓楼区", "rank_in_scene": 1, "in_scene_count": 2},
                       dist={"高端": 2}, content=["江南灶·融府", "亲子主题房"]),
                    _j("q2", ABSENT, same=True),
                ]
            }
        }
    }
    remaining = finalize_measurement(m)
    assert remaining == 0
    rate = m["platforms"]["deepseek"]["platform_rate"]
    assert rate["hit_rate"] == 0.5
    assert m["overall"]["overall_hit_rate"] == 0.5
    assert m["miss_structure"]["true_disadvantage"] == 1
    assert m["status"] == "complete"


def test_persona_rates():
    judgments = [
        _j("hit_family_size", RECOMMEND),
        _j("hit_family_avoid", ABSENT, same=True),
        _j("hit_business_generic", RECOMMEND),
    ]
    r = compute_persona_rates(judgments)
    assert r["family"]["valid"] == 2
    assert r["family"]["hit"] == 1
    assert r["family"]["hit_rate"] == 0.5
    assert r["business"]["hit_rate"] == 1.0


def test_platform_profile_normalized():
    # 每题 distribution 归一化成占比 → 跨题平均（题量大的题不主导）
    judgments = [
        _j("q1", RECOMMEND, dist={"高端": 2, "中端": 2}),   # 高端 50%
        _j("q2", ABSENT, same=True, dist={"高端": 1, "中端": 2}),  # 高端 33%
    ]
    r = aggregate_platform_profile(judgments)
    assert r["高端"] == round((0.5 + 1 / 3) / 2, 4)   # (50% + 33%)/2
    assert r["中端"] == round((0.5 + 2 / 3) / 2, 4)


def test_content_assets_frequency():
    judgments = [
        _j("q1", RECOMMEND, content=["江南灶·融府", "奶龙主题亲子房"]),
        _j("q2", MENTION, content=["江南灶·融府"]),
    ]
    r = aggregate_content_assets(judgments)
    assert r[0]["content"] == "江南灶·融府"
    assert r[0]["count"] == 2
    assert r[1]["count"] == 1


def test_overall_average():
    rates = {
        "deepseek": {"hit_rate": 0.9, "total": 20},
        "kimi": {"hit_rate": 0.6, "total": 20},
        "wenxin": {"hit_rate": 0.8, "total": 20},
        "doubao": {"hit_rate": 0.7, "total": 20},
    }
    r = compute_overall(rates)
    assert r["overall_hit_rate"] == 0.75   # (0.9+0.6+0.8+0.7)/4
    assert r["platform_hit_rates"]["kimi"] == 0.6


def test_effective_visibility():
    # 有效可见度 = 命中率 × (1 − β×负面率合成)，β=0.7 防双重惩罚（命中率已含部分负面影响）
    assert effective_visibility(0.3104, 0.1339) == 0.2813  # 31.04% × (1-0.7×13.39%)
    assert effective_visibility(0.5, 0) == 0.5              # 无负面
    assert effective_visibility(0.5, 0.2) == 0.43           # 负面 20% → β=0.7 打 86% 折
    assert effective_visibility(1.0, 1.0) == 0.3            # 全负面 → 1×(1-0.7)=0.3（非 0，防双重惩罚）
    # 折损系数可调
    assert effective_visibility(0.5, 0.2, beta=1.0) == 0.4  # β=1 退化为原公式


def test_effective_visibility_clamped():
    # 输出钳制：beta>1 且负面率高 → 不产出负值；输入越界钳到 [0,1]
    assert effective_visibility(1.0, 1.0, beta=1.5) == 0.0   # 1×(1-1.5)=-0.5 → 输出钳到 0
    assert effective_visibility(1.5, 0.5) == 0.65            # hit_rate 1.5→钳到1 → 1×(1-0.35)
    assert effective_visibility(0.5, -0.2) == 0.5            # 负面率负→钳到0 → 0.5×1


def _mk_close_measurement(decided=True):
    reco = RECOMMEND if decided else None
    return {
        "brand": "香格里拉", "city": "福州",
        "platforms": {
            "deepseek": {
                "judgments": [
                    _j("q1", reco, scene={"dim": "region", "val": "鼓楼区", "rank_in_scene": 1, "in_scene_count": 2},
                       has_hotel=True),
                ],
            },
        },
    }


def test_close_measurement_computes_all_derived():
    """spec ⑫ 唯一收口：一次算齐 effective_visibility + competitor_visibility。"""
    from src.collector.hit_rate import close_measurement

    m = _mk_close_measurement(decided=True)
    competitors = [
        {"name": "福州世茂洲际酒店", "band": "main"},
        {"name": "福州西湖大酒店", "band": "secondary"},
    ]
    sentiment = {
        "store_level": {"rate": 0.16, "status": "confirmed"},
        "brand_level": {"rate": 0.14, "status": "confirmed"},
    }
    remaining = close_measurement(m, competitors=competitors, sentiment=sentiment, city="福州")
    assert remaining == 0
    assert m["status"] == "complete"
    assert "effective_visibility" in m and m["effective_visibility_status"] == "confirmed"
    assert m["negative_rate_combined"] == round(0.8 * 0.16 + 0.2 * 0.14, 4)
    assert "competitor_visibility" in m
    assert m["competitor_visibility"]["overall"]["client_hit_rate"] == 1.0  # q1 recommend → 1/1


def test_close_measurement_clears_stale_derived():
    """spec ⑫ sealed 单一来源：重判时竞对/负面率输入缺 → 旧派生字段必须移除，不残留进新版本。"""
    from src.collector.hit_rate import close_measurement

    m = _mk_close_measurement(decided=True)
    comps = [{"name": "福州世茂洲际酒店", "band": "main"}]
    senti = {"store_level": {"rate": 0.16, "status": "confirmed"},
             "brand_level": {"rate": 0.14, "status": "confirmed"}}
    close_measurement(m, competitors=comps, sentiment=senti, city="福州")
    assert "competitor_visibility" in m and "effective_visibility" in m

    # 重判：竞对/负面率被清空 → 旧派生移除
    close_measurement(m, competitors=[], sentiment={}, city="福州")
    assert "competitor_visibility" not in m
    assert "effective_visibility" not in m
    assert "negative_rate_combined" not in m


def test_close_measurement_partial_when_undecided():
    """未判定 → status=partial、effective 无 sentiment 不产出、competitor 有效题为空（口径一致）。"""
    from src.collector.hit_rate import close_measurement

    m = _mk_close_measurement(decided=False)  # recommendation=None → needs_agent
    remaining = close_measurement(m, competitors=[{"name": "福州世茂洲际酒店", "band": "main"}],
                                  sentiment=None, city="福州")
    assert remaining == 1
    assert m["status"] == "partial"
    assert "effective_visibility" not in m          # 无 sentiment 输入 → 不产出
    assert m["competitor_visibility"]["platforms"]["deepseek"]["valid"] == 0  # 未判 → 无有效题
