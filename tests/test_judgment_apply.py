"""judgment apply 测试（A-2）：档位派生 + generate 待判清单 + apply 回填。"""

from src.collector.judgment import RECOMMEND, MENTION, ABSENT
from src.collector.judgment_apply import (
    derive_tier_distribution, generate_pending, apply_patch,
)


def _mk_measurement():
    """构造一个待判的 measurement（recommendation=None 的 judgment 骨架）。"""
    return {
        "platforms": {
            "deepseek": {
                "judgments": [
                    {
                        "question_id": "hit_business_generic",
                        "layer": "hit",
                        "platform": "deepseek",
                        "question": "福州出差住哪家酒店方便",
                        "answer": "1. 福州香格里拉大酒店\n2. 福州世茂洲际酒店",
                        "answer_form": "list",
                        "simple": True,
                        "client_present": True,
                        "rank": 1,
                        "brand_count": 2,
                        "recommendation": None,
                        "scene": None,
                        "same_tier_pushed": None,
                        "answer_tier_distribution": None,
                        "referred_content": [],
                        "has_hotel_recommendations": None,
                        "needs_agent": True,
                    },
                    {
                        "question_id": "hit_family_generic",
                        "layer": "hit",
                        "platform": "deepseek",
                        "question": "福州带娃住哪家酒店好",
                        "answer": "推荐悦华酒店",
                        "answer_form": "prose",
                        "simple": None,
                        "client_present": False,
                        "recommendation": None,
                        "scene": None,
                        "needs_agent": True,
                    },
                    {  # error 题：generate 应跳过
                        "question_id": "hit_solo_generic",
                        "layer": "hit",
                        "platform": "deepseek",
                        "answer": "",
                        "recommendation": None,
                        "reason": "error",
                        "needs_agent": False,
                    },
                ]
            }
        }
    }


def test_derive_distribution_known_brands():
    dist = derive_tier_distribution(
        ["福州香格里拉大酒店", "福州世茂洲际酒店", "福州悦华酒店"], city="福州"
    )
    assert dist == {"高端": 3}   # 香格里拉/洲际/悦华均高端


def test_derive_distribution_mixed_tiers():
    dist = derive_tier_distribution(["福州泰禾凯宾斯基酒店", "全季酒店", "汉庭酒店"], city="福州")
    assert dist.get("高端") == 1   # 凯宾斯基
    assert dist.get("中端") == 1   # 全季
    assert dist.get("经济") == 1   # 汉庭


def test_derive_distribution_unknown_brand_skipped():
    # 表外酒店（本地小旅馆）→ get_brand None → 不计入，不 crash
    dist = derive_tier_distribution(["福州香格里拉大酒店", "福州某小巷旅馆"], city="福州")
    assert dist == {"高端": 1}


def test_derive_distribution_empty():
    assert derive_tier_distribution([], city="福州") == {}


def test_generate_pending_skips_error_and_keeps_prefill():
    m = _mk_measurement()
    out = generate_pending(m)
    ds = out["platforms"]["deepseek"]
    assert "hit_solo_generic" not in ds            # error 题跳过
    assert set(ds) == {"hit_business_generic", "hit_family_generic"}
    item = ds["hit_business_generic"]
    assert item["question"] == "福州出差住哪家酒店方便"
    assert "福州香格里拉大酒店" in item["answer"]
    assert item["prefill"]["rank"] == 1


def test_generate_pending_and_apply_skip_attribution_layer():
    # 2026-09-13 对抗审查：归因题（recommendation=None）不得漏进命中判定待判清单/被 apply 污染
    m = _mk_measurement()
    m["platforms"]["deepseek"]["judgments"].append({
        "question_id": "attr_business",
        "layer": "attribution",
        "platform": "deepseek",
        "question": "福州香格里拉和福州世茂洲际酒店出差住哪家好，为什么",
        "answer": "世茂洲际位置更方便",
        "recommendation": None,
        "reason": "attribution_extracted",
        "needs_agent": False,
    })
    out = generate_pending(m)
    ds = out["platforms"]["deepseek"]
    assert "attr_business" not in ds               # 归因题不混进命中判定
    assert set(ds) == {"hit_business_generic", "hit_family_generic"}
    # 防御：apply_patch 对归因题也拒绝
    patch = {"deepseek": {"attr_business": {
        "recommendation": "recommend", "scene": None,
        "has_hotel_recommendations": True, "hotels_recommended": [],
    }}}
    applied = apply_patch(m, patch, city="福州", client_tier="高端")
    assert applied == 0
    attr_j = next(j for j in m["platforms"]["deepseek"]["judgments"] if j["question_id"] == "attr_business")
    assert attr_j["recommendation"] is None        # 归因题未被命中判定污染


def test_apply_patch_full_roundtrip():
    m = _mk_measurement()
    patch = {
        "deepseek": {
            "hit_business_generic": {
                "recommendation": RECOMMEND,
                "scene": {"dim": "region", "val": "鼓楼区", "rank_in_scene": 1, "in_scene_count": 2},
                "referred_content": ["江南灶·融府"],
                "has_hotel_recommendations": True,
                "hotels_recommended": ["福州香格里拉大酒店", "福州世茂洲际酒店", "福州悦华酒店"],
                "hotels_mentioned": ["福州泰禾凯宾斯基酒店"],
            },
            "hit_family_generic": {
                "recommendation": ABSENT,
                "scene": None,
                "has_hotel_recommendations": True,
                "hotels_recommended": ["福州悦华酒店"],
            },
        }
    }
    applied = apply_patch(m, patch, city="福州", client_tier="高端")
    assert applied == 2
    j = m["platforms"]["deepseek"]["judgments"][0]
    assert j["recommendation"] == RECOMMEND
    assert j["scene"]["rank_in_scene"] == 1
    assert j["referred_content"] == ["江南灶·融府"]
    assert j["answer_tier_distribution"] == {"高端": 3}   # 系统派生：香格里拉/洲际/悦华全高端
    assert j["same_tier_pushed"] is None                   # 真劣势锚定由 seal（close_measurement）用钉住竞对派生
    assert j["hotels_mentioned"] == ["福州泰禾凯宾斯基酒店"]  # 提及名单单独回填
    assert j["hit"] is True                                # 派生 hit = recommend
    assert j["needs_agent"] is False
    assert j["reason"] == "agent_finalized"
    # 未命中题（absent + 推了悦华）→ same_tier_pushed 待 seal 锚定（此处未 seal 不判）
    j2 = m["platforms"]["deepseek"]["judgments"][1]
    assert j2["recommendation"] == ABSENT
    assert j2["hit"] is False
    assert j2["same_tier_pushed"] is None


def test_apply_patch_mentioned_tier_does_not_trigger_disadvantage():
    # B 档核心：提及名单（背景）出现高端竞对，推荐名单只推中端 → same_tier_pushed=False（结构性）
    m = _mk_measurement()
    patch = {"deepseek": {"hit_business_generic": {
        "recommendation": ABSENT, "scene": None,
        "has_hotel_recommendations": True,
        "hotels_recommended": ["福州全季酒店"],        # 中端（推荐名单）
        "hotels_mentioned": ["福州世茂洲际酒店"],       # 高端（提及名单/背景）
    }}}
    applied = apply_patch(m, patch, city="福州", client_tier="高端")
    assert applied == 1
    j = m["platforms"]["deepseek"]["judgments"][0]
    assert j["hotels_recommended"] == ["福州全季酒店"]
    assert j["hotels_mentioned"] == ["福州世茂洲际酒店"]
    assert j["answer_tier_distribution"] == {"中端": 1}  # 档位只按推荐名单派生，提及不计
    assert j["same_tier_pushed"] is None                 # 真劣势锚定由 seal 派生（apply 阶段不判）
    assert j["hit"] is False


def test_apply_patch_invalid_recommendation_skipped():
    m = _mk_measurement()
    patch = {"deepseek": {"hit_business_generic": {"recommendation": "不确定", "hotels_recommended": []}}}
    applied = apply_patch(m, patch, city="福州", client_tier="高端")
    assert applied == 0
    assert m["platforms"]["deepseek"]["judgments"][0]["recommendation"] is None


def test_apply_patch_invalid_scene_dim_skipped():
    m = _mk_measurement()
    patch = {"deepseek": {"hit_business_generic": {
        "recommendation": RECOMMEND,
        "scene": {"dim": "星系", "val": "银河", "rank_in_scene": 1, "in_scene_count": 1},
        "hotels_recommended": [],
    }}}
    applied = apply_patch(m, patch, city="福州", client_tier="高端")
    assert applied == 0


def test_apply_patch_absent_mention_hit_false():
    m = _mk_measurement()
    patch = {"deepseek": {"hit_business_generic": {
        "recommendation": MENTION, "scene": None,
        "has_hotel_recommendations": True, "hotels_recommended": [],
    }}}
    apply_patch(m, patch, city="福州", client_tier="高端")
    assert m["platforms"]["deepseek"]["judgments"][0]["hit"] is False


def test_apply_patch_skips_already_judged_without_force():
    # 已判题（recommendation 非 None）→ 默认跳过，防重复 apply 静默覆盖
    m = _mk_measurement()
    j0 = m["platforms"]["deepseek"]["judgments"][0]
    j0["recommendation"] = "mention"   # 模拟已判
    j0["needs_agent"] = False
    patch = {"deepseek": {"hit_business_generic": {
        "recommendation": "recommend", "scene": None,
        "has_hotel_recommendations": True, "hotels_recommended": [],
    }}}
    applied = apply_patch(m, patch, city="福州", client_tier="高端")
    assert applied == 0
    assert j0["recommendation"] == "mention"   # 未被覆盖
    # force=True → 重判
    applied2 = apply_patch(m, patch, city="福州", client_tier="高端", force=True)
    assert applied2 == 1
    assert j0["recommendation"] == "recommend"


def test_apply_patch_missing_has_hotel_skipped():
    # 缺 has_hotel_recommendations（分母净化关键字段）→ 跳过，不留乐观默认
    m = _mk_measurement()
    patch = {"deepseek": {"hit_business_generic": {
        "recommendation": RECOMMEND, "scene": None, "hotels_recommended": [],
    }}}   # 无 has_hotel_recommendations
    applied = apply_patch(m, patch, city="福州", client_tier="高端")
    assert applied == 0
    assert m["platforms"]["deepseek"]["judgments"][0]["recommendation"] is None


def test_apply_patch_rejects_non_recommend_with_rank():
    """自洽硬约束（2026-09-05）：mention/exclude/absent 却带 scene.rank_in_scene≥1 → 拒绝
    （rank 隐含甲方被推荐，必须 recommend），防判定内部矛盾污染。"""
    m = _mk_measurement()
    patch = {"deepseek": {"hit_business_generic": {
        "recommendation": "mention",
        "scene": {"dim": "region", "val": "鼓楼区", "rank_in_scene": 1, "in_scene_count": 1},
        "has_hotel_recommendations": True, "hotels_recommended": [],
    }}}
    applied = apply_patch(m, patch, city="福州", client_tier="高端")
    assert applied == 0
    assert m["platforms"]["deepseek"]["judgments"][0]["recommendation"] is None
