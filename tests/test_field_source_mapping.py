"""P2 采集规则 — field_source_mapping + sentiment_query 加载测试。"""

from src.industry_knowledge.loader import IndustryKnowledgeLoader


class TestFieldSourceMapping:

    def test_load_11_fields(self):
        kb = IndustryKnowledgeLoader()
        items = kb.load_category("field_source_mapping")
        assert len(items) == 11
        assert any(i["id"] == "star_rating" for i in items)
        assert any(i["id"] == "competitors" for i in items)

    def test_each_field_has_queries_and_sources(self):
        kb = IndustryKnowledgeLoader()
        items = kb.load_category("field_source_mapping")
        for i in items:
            assert i.get("queries"), f"{i['id']} 缺 queries"
            assert i.get("sources"), f"{i['id']} 缺 sources"

    def test_queries_have_placeholders(self):
        """事实字段的 query 带 {品牌}{城市} 变量，竞品（枚举型）不带品牌。"""
        kb = IndustryKnowledgeLoader()
        items = kb.load_category("field_source_mapping")
        for i in items:
            if i["id"] == "competitors":
                for q in i["queries"]:
                    assert "{品牌}" not in q
            else:
                for q in i["queries"]:
                    assert "{品牌}" in q and "{城市}" in q, f"{i['id']} query 缺变量: {q}"

    def test_sources_use_t0_to_t4(self):
        kb = IndustryKnowledgeLoader()
        items = kb.load_category("field_source_mapping")
        valid = {"T0", "T1", "T2", "T3", "T4"}
        for i in items:
            for s in i["sources"]:
                assert s in valid, f"{i['id']} 非法 tier: {s}"

    def test_adr_uses_ota_not_official(self):
        """房价在 OTA(T1)+点评(T2)，不放官网(T0)。"""
        kb = IndustryKnowledgeLoader()
        adr = next(i for i in kb.load_category("field_source_mapping") if i["id"] == "adr")
        assert "T0" not in adr["sources"]


class TestSentimentQuery:

    def test_load_single_scope(self):
        """体系B（2026-10-14）：单档门店级，无品牌级。"""
        kb = IndustryKnowledgeLoader()
        items = kb.load_category("sentiment_query")
        assert len(items) == 1
        assert items[0]["id"] == "store_level"

    def test_queries_are_preset_literals(self):
        """体系B：词表硬编码（福州香格里拉），不参数化。"""
        kb = IndustryKnowledgeLoader()
        store = kb.load_category("sentiment_query")[0]
        assert len(store["queries"]) == 20
        assert all("福州香格里拉" in q for q in store["queries"])
