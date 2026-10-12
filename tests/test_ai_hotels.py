"""AI 推荐酒店提取测试：从命中层回答提取酒店 + 与甲方同场景共现。

同场景共现 = AI 在提到甲方的题目里也提到该酒店的次数（替代关系信号，
区别于总提及——总提及含声量、共现含替代）。
"""
from src.collector.ai_hotels import extract_hotels


def _j(qid, q, answer):
    return {"question_id": qid, "question": q, "answer": answer}


def test_extract_hotels_mentions_and_cooccurrence():
    judgments = [
        _j("hit_business_generic", "福州出差住哪家酒店方便",
           "推荐福州世茂洲际酒店和福州香格里拉大酒店，出差都方便"),
        _j("hit_business_breakfast", "福州出差住哪家酒店含早餐",
           "福州香格里拉大酒店含早餐，三迪希尔顿酒店也含"),
        _j("hit_family_generic", "福州带娃住哪家酒店好",
           "福州悦华酒店适合带娃，有亲子房"),
    ]
    out = extract_hotels(judgments, client_brand="香格里拉")

    # 世茂洲际：题1 与甲方同题 → 共现 1
    assert out["世茂洲际酒店"]["mentions"] == 1
    assert out["世茂洲际酒店"]["cooccurrence"] == 1
    # 三迪希尔顿：题2 与甲方同题 → 共现 1
    assert out["三迪希尔顿酒店"]["cooccurrence"] == 1
    # 悦华：题3 不含甲方 → 共现 0（有声量无替代）
    assert out["悦华酒店"]["mentions"] == 1
    assert out["悦华酒店"]["cooccurrence"] == 0


def test_extract_hotels_excludes_client_brand():
    judgments = [
        _j("hit_business_generic", "福州出差住哪家酒店方便",
           "福州香格里拉大酒店是首选"),
    ]
    out = extract_hotels(judgments, client_brand="香格里拉")
    assert "香格里拉大酒店" not in out  # 甲方自身不算竞对


def test_extract_hotels_normalizes_city_prefix():
    judgments = [
        _j("hit_business_generic", "福州出差住哪家酒店方便",
           "福州三迪希尔顿酒店不错，悦华酒店也可以"),
    ]
    out = extract_hotels(judgments, client_brand="香格里拉")
    # 城市前缀去掉 → 统一归一化
    assert "三迪希尔顿酒店" in out
    assert "福州三迪希尔顿酒店" not in out


def test_extract_hotels_ignores_non_hotel_phrases():
    judgments = [
        _j("hit_business_generic", "福州出差住哪家酒店方便",
           "推荐几家酒店，这家酒店性价比高，那家酒店离高铁站近"),
    ]
    out = extract_hotels(judgments, client_brand="香格里拉")
    assert out == {}  # "这家酒店/那家酒店" 非实体，忽略


def test_extract_hotels_empty_judgments():
    assert extract_hotels([], client_brand="香格里拉") == {}


def test_extract_hotels_connection_word_prefix():
    # "和福建外贸中心悦华酒店" → 连接词"和"清洗 + 剥福建前缀，不碎片化
    judgments = [_j("q", "福州出差住哪家酒店方便",
                    "推荐福州世茂洲际酒店和福建外贸中心悦华酒店")]
    out = extract_hotels(judgments, client_brand="香格里拉")
    assert "世茂洲际酒店" in out
    assert "外贸中心悦华酒店" in out  # 剥福州/福建前缀
    assert "和福建外贸中心悦华酒店" not in out
    assert "如家酒店" not in out  # "如"不在清洗前缀，不误伤如家品牌


def test_extract_hotels_brand_home_inn_not_harmed():
    # 连接词前缀不含"如"，如家酒店不被误剥
    judgments = [_j("q", "福州一个人住性价比高的酒店", "福州如家酒店性价比高")]
    out = extract_hotels(judgments, client_brand="香格里拉")
    assert "如家酒店" in out


def test_extract_hotels_city_prefix_parameterized():
    # 跨地区：city 参数化剥"广州"前缀（换地区通用，不硬编码福州）
    judgments = [_j("q", "广州住哪方便", "广州花园酒店不错，白天鹅宾馆也好")]
    out = extract_hotels(judgments, client_brand="香格里拉", city="广州")
    assert "花园酒店" in out
    assert "白天鹅宾馆" in out
    assert "广州花园酒店" not in out


def test_extract_hotels_client_mixed_with_others():
    # 甲方品牌与其他酒店无标点混写 → 剥离甲方后提取其他酒店（不整段误排除）
    judgments = [_j("q", "广州出差住哪家酒店方便", "广州香格里拉和广州花园酒店都不错")]
    out = extract_hotels(judgments, client_brand="香格里拉", city="广州")
    assert "花园酒店" in out
    assert not any("香格里拉" in k for k in out)
