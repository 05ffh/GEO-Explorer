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

    def test_store_level_has_city(self):
        queries = build_sentiment_queries("香格里拉", "广州")
        store = [q for q in queries if q["field"] == "store_level"]
        assert store, "门店级 query 应存在"
        assert any("广州" in q["query"] for q in store)

    def test_brand_level_no_city(self):
        queries = build_sentiment_queries("香格里拉", "广州")
        brand = [q for q in queries if q["field"] == "brand_level"]
        assert brand, "品牌级 query 应存在"
        for q in brand:
            assert "广州" not in q["query"]

    def test_city_none_only_brand_level(self):
        queries = build_sentiment_queries("香格里拉", city=None)
        assert all(q["field"] == "brand_level" for q in queries)

    def test_negative_recall_words_present(self):
        """负面倾向搜索词（spec 4.5 双形态）：门店级 UGC 差评 + 品牌级舆情新闻。"""
        queries = build_sentiment_queries("香格里拉", "福州")
        store = [q["query"] for q in queries if q["field"] == "store_level"]
        brand = [q["query"] for q in queries if q["field"] == "brand_level"]
        # UGC 差评形态
        assert any("差评" in q for q in store)
        assert any("投诉" in q for q in store)
        assert any("踩雷" in q for q in store)
        # 舆情新闻形态
        assert any("曝光" in q for q in brand)
        assert any("约谈" in q for q in brand)
        assert any("处罚" in q for q in brand)
        # 总量分母仍保留（评价/推荐/口碑）
        assert any("评价" in q for q in store)
        assert any("口碑" in q for q in brand)
