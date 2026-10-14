"""搜索词生成器测试。"""

from src.collector.query_builder import build_search_queries, build_sentiment_queries


class TestBuildSearchQueries:

    def test_generates_queries_with_brand_and_city(self):
        queries = build_search_queries("香格里拉", "广州")
        # 找到 star_rating 字段的 query，验证变量已填充
        star = [q for q in queries if q["field"] == "star_rating"]
        assert any("香格里拉" in q["query"] and "广州" in q["query"] for q in star)
        assert any("几星" in q["query"] for q in star)

    def test_no_unfilled_placeholders(self):
        queries = build_search_queries("香格里拉", "广州")
        for q in queries:
            assert "{品牌}" not in q["query"], f"未填充品牌: {q['query']}"
            assert "{城市}" not in q["query"], f"未填充城市: {q['query']}"

    def test_competitors_has_no_brand(self):
        """竞品是枚举型，找的是"别人"，不带品牌名。"""
        queries = build_search_queries("香格里拉", "广州")
        comp = [q for q in queries if q["field"] == "competitors"]
        for q in comp:
            assert "香格里拉" not in q["query"]

    def test_sources_preserved(self):
        queries = build_search_queries("香格里拉", "广州")
        star = next(q for q in queries if q["field"] == "star_rating")
        assert "T0" in star["sources"] and "T1" in star["sources"]


class TestBuildSentimentQueries:

    def test_single_scope_store_level(self):
        """体系B 单档（2026-10-14）：只有 store_level，词表硬编码福州香格里拉（不参数化）。"""
        queries = build_sentiment_queries("香格里拉", "广州")
        assert queries and all(q["field"] == "store_level" for q in queries)
        assert all("福州香格里拉" in q["query"] for q in queries)  # 硬编码，与传入品牌/城市无关
        assert len(queries) == 20

    def test_city_none_same_words(self):
        queries = build_sentiment_queries("香格里拉", "福州")
        assert all(q["field"] == "store_level" for q in queries)

    def test_negative_recall_words_present(self):
        """负面倾向搜索词覆盖差评/投诉/卫生/押金…（体系B 词表）。"""
        store = [q["query"] for q in build_sentiment_queries("香格里拉", "福州")]
        assert any("差评" in q for q in store)
        assert any("投诉" in q for q in store)
        assert any("卫生" in q for q in store)
        assert any("押金" in q for q in store)
