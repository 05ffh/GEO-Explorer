"""竞对判定测试（确定性部分，spec 3.1 竞对区域圈层·系统化承载）。

系统判确定性：ADR 带（甲方 ±50%）+ 档位（±1）；ring/format/去重 由主 agent 提供。
"""
from src.collector.competitor import adr_band, filter_competitors, select_primary, tier_in_span


def test_adr_band():
    lo, hi = adr_band(850)
    assert lo == 425.0 and hi == 1275.0


def test_adr_band_custom_ratio():
    lo, hi = adr_band(1000, ratio=0.3)
    assert lo == 700.0 and hi == 1300.0


def test_tier_in_span():
    assert tier_in_span("中高端", "高端") is True
    assert tier_in_span("高端", "高端") is True
    assert tier_in_span("豪华", "高端") is True
    assert tier_in_span("中端", "高端") is False
    assert tier_in_span("经济", "高端") is False


def test_filter_competitors_marks_band_and_span():
    candidates = [
        {"name": "A", "adr": 700, "tier": "高端"},   # 带内 + 档位内
        {"name": "B", "adr": 2000, "tier": "高端"},  # ADR 带外
        {"name": "C", "adr": 900, "tier": "中端"},   # 档位带外
    ]
    out = filter_competitors(candidates, client_tier="高端", client_adr=850)
    assert out[0]["adr_in_band"] is True and out[0]["tier_in_span"] is True
    assert out[1]["adr_in_band"] is False
    assert out[2]["tier_in_span"] is False
    # 依据链：ADR 带边界带进输出，供主 agent 复核
    assert out[0]["adr_band"] == [425.0, 1275.0]


def test_select_primary_core_same_tier_nearest_adr():
    comps = [
        {"name": "核心A", "ring": "核心", "tier": "高端", "adr": 900},
        {"name": "核心B", "ring": "核心", "tier": "高端", "adr": 700},
    ]
    p = select_primary(comps, client_tier="高端", client_adr=850)
    assert p["name"] == "核心A"  # 900 最接近 850


def test_select_primary_falls_back_near_ring():
    comps = [
        {"name": "近邻", "ring": "近邻", "tier": "高端", "adr": 800},
    ]
    p = select_primary(comps, client_tier="高端", client_adr=850)
    assert p["name"] == "近邻"


def test_select_primary_none_when_empty():
    assert select_primary([], client_tier="高端") is None


def test_select_primary_no_client_adr_takes_first():
    comps = [
        {"name": "核心A", "ring": "核心", "tier": "高端"},
        {"name": "核心B", "ring": "核心", "tier": "高端"},
    ]
    p = select_primary(comps, client_tier="高端")
    assert p["name"] == "核心A"


def test_select_primary_ignores_adr_none():
    # 给定甲方 ADR 时，无 ADR 候选不参与"最接近"排序（防被当距离 0 作弊胜出）
    comps = [
        {"name": "无ADR", "ring": "核心", "tier": "高端"},
        {"name": "ADR900", "ring": "核心", "tier": "高端", "adr": 900},
    ]
    p = select_primary(comps, client_tier="高端", client_adr=850)
    assert p["name"] == "ADR900"


def test_select_primary_standard_over_boutique():
    # 精品业态不作主竞对（业态是报告弱标注，主竞对应是标准酒店）
    comps = [
        {"name": "精品安民", "ring": "核心", "tier": "高端", "adr": 800, "format": "精品"},
        {"name": "标准凯宾", "ring": "核心", "tier": "高端", "adr": 750, "format": "标准"},
    ]
    p = select_primary(comps, client_tier="高端", client_adr=850)
    assert p["name"] == "标准凯宾"


def test_select_primary_guest_mix_priority():
    # 客群匹配优先：商务甲方选商务客群竞对，即使 AI 共现/ADR 不占优
    comps = [
        {"name": "商务洲际", "ring": "核心", "tier": "高端", "adr": 900, "guest_mix": ["商务差旅"], "ai_cooccurrence": 2},
        {"name": "亲子悦华", "ring": "核心", "tier": "高端", "adr": 850, "guest_mix": ["亲子家庭"], "ai_cooccurrence": 8},
    ]
    p = select_primary(comps, client_tier="高端", client_adr=850, client_guest="商务差旅")
    assert p["name"] == "商务洲际"


def test_select_primary_ai_cooccurrence_priority():
    # 同客群下 AI 同场景共现优先于 ADR 距离
    comps = [
        {"name": "低共现", "ring": "核心", "tier": "高端", "adr": 880, "ai_cooccurrence": 2},
        {"name": "高共现", "ring": "核心", "tier": "高端", "adr": 900, "ai_cooccurrence": 11},
    ]
    p = select_primary(comps, client_tier="高端", client_adr=850)
    assert p["name"] == "高共现"


def test_select_primary_no_signal_falls_back_adr():
    # 无客群/AI 信号时退回 ADR 最近
    comps = [
        {"name": "A", "ring": "核心", "tier": "高端", "adr": 900},
        {"name": "B", "ring": "核心", "tier": "高端", "adr": 860},
    ]
    p = select_primary(comps, client_tier="高端", client_adr=850)
    assert p["name"] == "B"


def test_primary_to_attribution_question_integration():
    # 端到端：结构化竞对 → select_primary 主竞对名 → build_questions 归因题用它（P3 归因层消费）
    from src.collector.question_builder import build_questions

    comps = [
        {"name": "福州世茂洲际酒店", "ring": "核心", "tier": "高端", "adr": 700},
        {"name": "福州三迪希尔顿酒店", "ring": "近邻", "tier": "高端", "adr": 850},
    ]
    primary = select_primary(comps, client_tier="高端", client_adr=850)
    qs = build_questions("香格里拉", "福州", tier="高端", competitor=primary["name"])
    attr = [q for q in qs if q["layer"] == "attribution"]
    assert len(attr) == 10   # 5 对比 + 5 平衡（P1-② 决策2，2026-09-10）
    assert all("福州世茂洲际酒店" in q["question"] for q in attr)
    assert all("福州香格里拉" in q["question"] for q in attr)   # 甲方带地区（2026-09-13）
