"""档位评定测试：品牌梯队(adr_reference 校准) + ADR 区间 + 星级下限/上限。

2026-09-01 重设计：去顶奢加中高端，品牌表存 tier+adr_range 双字段。
"""

from src.collector.query_builder import build_search_queries
from src.collector.tier import TIER_WORD, TIER_BUDGET, derive_tier, get_brand_tier


def test_get_brand_tier_known():
    assert get_brand_tier("香格里拉") == "高端"
    assert get_brand_tier("宝格丽") == "豪华"  # 原顶奢 → 并入豪华
    assert get_brand_tier("安缦") == "豪华"
    assert get_brand_tier("如家") == "经济"


def test_get_brand_tier_unknown():
    assert get_brand_tier("某长尾酒店") is None


def test_get_brand_tier_substring_direction():
    # 回归：子串匹配方向反了会把"万豪"误匹配到"JW万豪"
    assert get_brand_tier("万豪") == "高端"
    assert get_brand_tier("JW万豪") == "高端"  # 2026-09-02 中国市场档位（与香格里拉同档）
    assert get_brand_tier("JW") is None


def test_get_brand_tier_child_brand_wins():
    # 最长子串优先：希尔顿欢朋命中"希尔顿欢朋"(4字)而非"希尔顿"(2字)
    assert get_brand_tier("福州希尔顿欢朋酒店") == "中端"
    assert get_brand_tier("福州三迪希尔顿酒店") == "高端"


def test_derive_tier_client_specified_first():
    assert derive_tier("香格里拉", client_specified="经济") == "经济"


def test_derive_tier_brand_tier_no_adr():
    # 无 ADR 时用品牌行政档位
    assert derive_tier("香格里拉") == "高端"
    assert derive_tier("安缦") == "豪华"


def test_derive_tier_brand_adr_reference_calibration():
    # 门店 ADR 低于品牌参考带 → 取市场价落点（福州洲际 700<800 → 高端）
    assert derive_tier("洲际", adr=700) == "高端"
    assert derive_tier("凯宾斯基", adr=750) == "高端"
    # ADR 在带内 → 品牌档位（洲际 2026-09-02 改中国市场高端，900∈[800,2000] → 高端）
    assert derive_tier("洲际", adr=900) == "高端"
    # 希尔顿欢朋匹配希尔顿品牌，但 ADR 350 落中端（不误判高端）
    assert derive_tier("福州希尔顿欢朋酒店", adr=350) == "中端"
    assert derive_tier("香格里拉", adr=850) == "高端"


def test_derive_tier_adr_fallback():
    # 表外品牌 ADR 落点：经济<250 / 中端250-400 / 中高端400-700 / 高端700-1500 / 豪华>=1500
    assert derive_tier("某长尾", adr=1600) == "豪华"
    assert derive_tier("某长尾", adr=900) == "高端"
    assert derive_tier("某长尾", adr=600) == "中高端"
    assert derive_tier("某长尾", adr=350) == "中端"
    assert derive_tier("某长尾", adr=200) == "经济"
    # 边界（等于分界值归高档）
    assert derive_tier("某长尾", adr=1500) == "豪华"
    assert derive_tier("某长尾", adr=700) == "高端"
    assert derive_tier("某长尾", adr=400) == "中高端"
    assert derive_tier("某长尾", adr=250) == "中端"


def test_derive_tier_brand_adr_above_range_upgrades():
    # 品牌 ADR 高于参考带 → 市场价升档（经济品牌如家卖 300 → 中端）
    assert derive_tier("如家", adr=300) == "中端"
    assert derive_tier("汉庭", adr=600) == "中高端"


def test_derive_tier_brand_path_ignores_star():
    # 品牌命中时星级不影响（品牌档位已综合）；洲际@700 校准为高端
    assert derive_tier("洲际", adr=700, star_rating="五星") == "高端"


def test_derive_tier_star_variant_normalized():
    # 星级输入变体归一化："5星"→五星、"四星级"→四星
    assert derive_tier("某长尾", star_rating="5星") == "高端"
    assert derive_tier("某长尾", star_rating="四星级") == "中端"
    assert derive_tier("某长尾", adr=900, star_rating="3星") == "中端"


def test_derive_tier_star_clamp():
    # 五星 → 至少高端（ADR 落中高端也抬到高端）
    assert derive_tier("某长尾", adr=600, star_rating="五星") == "高端"
    # 四星 → 至少中端
    assert derive_tier("某长尾", adr=600, star_rating="四星") == "中高端"
    assert derive_tier("某长尾", adr=200, star_rating="四星") == "中端"
    # 三星 → 至多中端（ADR 落高端也压到中端）
    assert derive_tier("某长尾", adr=900, star_rating="三星") == "中端"


def test_derive_tier_star_fallback():
    assert derive_tier("某长尾", star_rating="五星") == "高端"
    assert derive_tier("某长尾", star_rating="四星") == "中端"
    assert derive_tier("某长尾", star_rating="三星") == "经济"


def test_derive_tier_unknown():
    assert derive_tier("某长尾") is None


def test_tier_word_no_dingshe_has_zhonggaoduan():
    assert "顶奢" not in TIER_WORD
    assert "中高端" in TIER_WORD
    assert TIER_WORD["中高端"] == "中高档的"


def test_tier_budget_has_zhonggaoduan():
    assert TIER_BUDGET["中高端"] == "800"
    assert TIER_BUDGET["高端"] == "1500"
    assert "顶奢" not in TIER_BUDGET


def test_competitor_query_uses_tier_word():
    queries = build_search_queries("香格里拉", "福州")
    comp = [q for q in queries if q["field"] == "competitors"]
    assert comp
    # 甲方高端 → ±1 档多档位词召回：中高档的/高端的/五星级的
    texts = [q["query"] for q in comp]
    assert any("中高档的" in t for t in texts)
    assert any("高端的" in t for t in texts)
    assert any("五星级的" in t for t in texts)


def test_unknown_tier_skips_competitor_queries():
    # 档位未定 → 跳过竞品查询词，不静默假设"高端"
    queries = build_search_queries("某长尾酒店", "福州")
    comp = [q for q in queries if q["field"] == "competitors"]
    assert comp == []


def test_tier_span():
    from src.collector.tier import tier_span

    assert tier_span("高端") == ["中高端", "高端", "豪华"]
    assert tier_span("经济") == ["经济", "中端"]  # 首档不越界
    assert tier_span("豪华") == ["高端", "豪华"]  # 尾档不越界
    assert tier_span("某档") == ["某档"]          # 表外回退


def test_derive_tier_local_brand_region_filter():
    # 本地品牌（region=福州）：本地区匹配，换地区（广州）不误用 → 表外 ADR 兜底
    assert derive_tier("福州悦华酒店", adr=750, city="福州") == "高端"  # region 匹配
    assert derive_tier("福州悦华酒店", city="广州") is None            # region 不匹配 → 表外
    assert derive_tier("福州悦华酒店", adr=750, city="广州") == "高端"  # 表外 ADR 兜底
    # 全国连锁无 region，任何城市通用
    assert derive_tier("洲际", city="广州") == "高端"
    assert derive_tier("香格里拉", city="广州") == "高端"


def test_derive_tier_city_normalized():
    # city 归一化："福州市" → "福州"，region 精确匹配
    assert derive_tier("福州悦华酒店", adr=750, city="福州市") == "高端"
    assert derive_tier("福州悦华酒店", adr=750, city="福州市") == "高端"


def test_derive_tier_unconditional_luxury():
    # 顶级品牌无条件豪华：宝格丽 ADR 低也不降档（unconditional 跳过校准）
    assert derive_tier("宝格丽", adr=700) == "豪华"
    assert derive_tier("宝格丽", adr=3000) == "豪华"
    assert derive_tier("四季", adr=500) == "豪华"
    # 普通高端品牌仍校准（洲际 ADR 700 → 高端）
    assert derive_tier("洲际", adr=700) == "高端"


def test_get_brand_tier_no_city_hits_local():
    # get_brand_tier 不传 city：本地品牌不过滤命中（生产无调用，测试/辅助用）
    assert get_brand_tier("悦华") == "高端"
    assert get_brand_tier("悦华", city="福州") == "高端"
    assert get_brand_tier("悦华", city="广州") is None  # 传 city 则过滤


def test_get_brand_tier_separator_normalization():
    # 间隔号归一化（2026-09-05）：带·/不带·的本地品牌名都匹配同一条目，
    # 且"四季·悦城"不被国际"四季"（豪华）误配
    assert get_brand_tier("福州四季·悦城酒店", "福州") == "高端"
    assert get_brand_tier("福州四季悦城酒店", "福州") == "高端"
    assert get_brand_tier("福州西湖宾馆", "福州") == "高端"       # 本地补充
    assert get_brand_tier("福州中海凯骊酒店", "福州") == "高端"
    assert get_brand_tier("颐豪酒店（福州南站店）", "福州") == "中高端"
    assert get_brand_tier("三坊七巷美居温泉酒店", "福州") == "中高端"  # 国际品牌不受影响
