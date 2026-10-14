"""question_builder 实例化测试：变量填充、可选片段泛化、档位/竞品缺失跳过。"""
import pytest

from src.collector.question_builder import build_questions, _instantiate


def _by_id(qs, qid):
    return next(q for q in qs if q["id"] == qid)


def test_full_instantiation_35_questions():
    # 25 命中 + 10 归因（5 对比 + 5 平衡，P1-② 决策2）
    qs = build_questions("香格里拉", "福州", tier="高端", competitor="希尔顿",
                         attraction="三坊七巷", budget="500")
    assert len(qs) == 35
    # 无变量残留
    assert all("{" not in q["question"] for q in qs)
    assert sum(q["layer"] == "attribution" for q in qs) == 10


def test_scenario_competitors_injected_per_persona():
    # 场景匹配竞对（P1-②）：每道归因题按该场景 persona 注入各自头号对手，不全部用单竞对
    sc = {"商务差旅": "福州世茂洲际酒店", "亲子家庭": "福州西湖大酒店",
          "情侣度假": "福州世茂洲际酒店", "朋友结伴": "福州泰禾凯宾斯基酒店", "单人出行": "福州世茂洲际酒店"}
    qs = build_questions("福州香格里拉", "福州", tier="高端", competitor="福州世茂洲际酒店",
                         scenario_competitors=sc)
    assert "福州西湖大酒店" in _by_id(qs, "attr_family")["question"]      # 带娃 → 西湖（次竞对）
    assert "福州泰禾凯宾斯基酒店" in _by_id(qs, "attr_friends")["question"]  # 朋友 → 凯宾斯基
    assert "福州世茂洲际酒店" in _by_id(qs, "attr_business")["question"]
    # 命中层不受影响（仍 25 题）
    assert sum(q["layer"] == "hit" for q in qs) == 25


def test_tier_word_filled():
    qs = build_questions("香格里拉", "福州", tier="高端")
    q = _by_id(qs, "hit_business_transit")
    assert q["question"] == "福州高铁站附近有什么高端的酒店"


def test_attraction_generic_when_missing():
    qs = build_questions("香格里拉", "福州")
    q = _by_id(qs, "hit_family_attraction")
    assert q["question"] == "福州带娃住哪方便"  # [{景点}附近] 整段删除


def test_attraction_filled():
    qs = build_questions("香格里拉", "福州", attraction="三坊七巷")
    q = _by_id(qs, "hit_family_attraction")
    assert q["question"] == "福州三坊七巷附近带娃住哪方便"


def test_budget_generic_when_missing():
    qs = build_questions("香格里拉", "福州")
    q = _by_id(qs, "hit_solo_budget")
    assert q["question"] == "福州交通方便的酒店"  # [预算{预算}元以内、] 删除


def test_budget_filled():
    qs = build_questions("香格里拉", "福州", budget="500")
    q = _by_id(qs, "hit_solo_budget")
    assert q["question"] == "福州预算500元以内、交通方便的酒店"


def test_budget_derived_from_tier():
    # 不显式传 budget，tier="高端" → 价格带上限 1500（2026-09-01 档位区间校准：高端 700-1500）
    qs = build_questions("香格里拉", "福州", tier="高端")
    q = _by_id(qs, "hit_solo_budget")
    assert q["question"] == "福州预算1500元以内、交通方便的酒店"


def test_tier_undefined_skips_tier_questions():
    qs = build_questions("香格里拉", "福州", tier=None)
    # 5 个档位词题被跳过，命中层 25 → 20
    hit = [q for q in qs if q["layer"] == "hit"]
    assert len(hit) == 20
    assert all("{档次词}" not in q["question"] for q in qs)


def test_competitor_missing_skips_attribution():
    qs = build_questions("香格里拉", "福州", tier="高端", competitor=None)
    attr = [q for q in qs if q["layer"] == "attribution"]
    assert len(attr) == 0
    assert len(qs) == 25  # 命中层全出


def test_attribution_filled():
    qs = build_questions("香格里拉", "福州", competitor="希尔顿")
    q = _by_id(qs, "attr_business")
    # 2026-09-13：归因题点名甲方+竞对都带地区限定（否则 AI 对比回答漂移）
    assert q["question"] == "福州香格里拉和福州希尔顿出差住哪家好，为什么"


def test_attribution_region_qualified():
    # 甲方裸品牌补城市；竞对已是完整店名/含城市则不动
    qs = build_questions("香格里拉", "福州", competitor="福州世茂洲际酒店")
    q = _by_id(qs, "attr_business")
    assert q["question"] == "福州香格里拉和福州世茂洲际酒店出差住哪家好，为什么"
    # 省前缀完整店名不重复补城市
    qs2 = build_questions("香格里拉", "福州", competitor="福建外贸中心悦华酒店")
    assert "福州福建" not in _by_id(qs2, "attr_business")["question"]
    # brand 已带城市不重复补（换地区复用场景）
    qs3 = build_questions("福州香格里拉", "福州", competitor="希尔顿")
    assert "福州福州" not in _by_id(qs3, "attr_business")["question"]
    assert "福州香格里拉" in _by_id(qs3, "attr_business")["question"]


def test_instantiate_optional_keeps_filled():
    # 直接测 _instantiate 的保留分支
    out = _instantiate("{城市}[预算{预算}元、]酒店", {"城市": "福州", "预算": "500"})
    assert out == "福州预算500元、酒店"


def test_missing_brand_or_city_raises():
    with pytest.raises(ValueError):
        build_questions("", "福州")
    with pytest.raises(ValueError):
        build_questions("香格里拉", "")


def test_system_b_client_hit_layer():
    """体系B（spec 3.1.2）：命中层=甲方指定（18 题硬编码）+ 归因层=共用体系A（10 题）= 28。"""
    qs = build_questions("香格里拉", "福州", tier="高端", competitor="希尔顿", system="B")
    assert len(qs) == 28
    hit = [q for q in qs if q["layer"] == "hit"]
    attr = [q for q in qs if q["layer"] == "attribution"]
    assert len(hit) == 18 and len(attr) == 10
    assert all("{" not in q["question"] for q in hit)      # 硬编码，无变量
    assert any("福州市中心" in q["question"] for q in hit)
    # 归因层与体系A 一致（两套共用）
    assert _by_id(qs, "attr_business")["question"] == "福州香格里拉和福州希尔顿出差住哪家好，为什么"
