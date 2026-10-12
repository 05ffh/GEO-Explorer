"""brand_domains 信任测试（2026-09-10）：schema 校验 + 关键品牌档位/竞对带回归。"""

import pytest

from src.industry_knowledge.loader import validate_brand_domains, get_knowledge_loader
from src.collector.tier import get_brand
from src.collector.competitor import classify_band, COMPETITOR_BAND_MAIN, COMPETITOR_BAND_SECONDARY


# ── schema 校验（loader 层 fail-fast）──

def test_validate_brand_domains_ok():
    assert validate_brand_domains(get_knowledge_loader().load_category("brand_domains")) == []


def test_validate_catches_bad_tier_and_missing_zh():
    errs = validate_brand_domains([
        {"id": "a", "tier": "超豪华", "zh": "A"},
        {"id": "b", "tier": "高端"},
    ])
    assert any("非法 tier" in e for e in errs)     # 超豪华 非法
    assert any("缺 zh" in e for e in errs)          # b 缺 zh


def test_validate_catches_dup_id_and_bad_adr():
    errs = validate_brand_domains([
        {"id": "x", "tier": "高端", "zh": "X", "adr_range": [500, 1500]},
        {"id": "x", "tier": "中端", "zh": "Y"},
        {"id": "z", "tier": "高端", "zh": "Z", "adr_range": [2000, 1000]},
    ])
    assert any("重复 id" in e for e in errs)
    assert any("adr_range 非法" in e for e in errs)


# ── 关键品牌档位/竞对带回归（当前诊断链路依赖的品牌）──

def test_key_brand_international_five_star_main_band():
    # 甲方 + 主竞对：国际五星同档 → main band
    for name in ("福州香格里拉大酒店", "福州世茂洲际酒店", "福州泰禾凯宾斯基酒店", "福州中庚喜来登"):
        brand = get_brand(name, city="福州")
        assert brand is not None, name
        assert brand["tier"] == "高端", name
        assert classify_band(brand) == COMPETITOR_BAND_MAIN, name


def test_key_brand_local_high_end_secondary_band():
    # 次竞对：福州本地高端 → secondary band
    for name in ("福州西湖大酒店", "福建外贸中心悦华酒店"):
        brand = get_brand(name, city="福州")
        assert brand is not None, name
        assert brand["tier"] == "高端", name
        assert classify_band(brand) == COMPETITOR_BAND_SECONDARY, name


def test_key_brand_mid_tier_structural_reference():
    # 结构性判定参照：全季=中端（推了不算甲方竞技场），汉庭=经济
    assert get_brand("全季酒店", city="福州")["tier"] == "中端"
    assert get_brand("福州全季酒店", city="福州")["tier"] == "中端"
    assert get_brand("汉庭酒店", city="福州")["tier"] == "经济"


def test_key_brands_have_tier_source_provenance():
    # provenance：国际五星=brand（官方定位），本地=manual（主 agent 认定）
    items = {i["id"]: i for i in get_knowledge_loader().load_category("brand_domains")}
    for iid in ("shangri_la", "intercontinental", "kempinski", "sheraton", "ji_hotel", "hanting"):
        assert items[iid]["tier_source"] == "brand", iid
    for iid in ("yuehua", "west_lake_hotel"):
        assert items[iid]["tier_source"] == "manual", iid
