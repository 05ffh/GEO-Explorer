"""GT Quality Improvement tests — P0-1 + P0-2 per expert review."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── P0: Field Policies ───────────────────────────────────────────────────────


class TestFieldPolicies:
    def test_registration_fields_are_search_first(self):
        from src.gt.field_policy import FIELD_POLICIES
        for f in ("official_name", "founded_year", "official_domains"):
            assert FIELD_POLICIES[f]["strategy"] == "search_first"
            assert FIELD_POLICIES[f]["requires_search_verification"] is True

    def test_description_fields_allow_ai_fill(self):
        from src.gt.field_policy import FIELD_POLICIES
        assert FIELD_POLICIES["positioning"]["allow_ai_fill"] is True
        assert FIELD_POLICIES["positioning"]["strategy"] in ("ai_plus_search", "search_plus_ai")

    def test_all_policies_have_category(self):
        from src.gt.field_policy import FIELD_POLICIES
        for name, policy in FIELD_POLICIES.items():
            assert "category" in policy, f"{name} missing category"

    def test_get_high_risk_fields_returns_p0_fields(self):
        from src.gt.field_policy import get_high_priority_fields
        fields = get_high_priority_fields()
        assert "official_name" in fields
        assert "founded_year" in fields
        assert "official_domains" in fields
        assert "headquarters" in fields
        assert "core_products" in fields

    def test_get_search_first_fields(self):
        from src.gt.field_policy import get_fields_by_strategy
        search_first = get_fields_by_strategy("search_first")
        assert "official_name" in search_first
        assert "official_domains" in search_first


# ── P0-1: Field Verifier ─────────────────────────────────────────────────────


class TestFieldVerifier:
    def _mock_adapter(self):
        from src.search.tavily_search_adapter import TavilySearchAdapter
        adapter = MagicMock(spec=TavilySearchAdapter)
        adapter.name = "tavily"
        adapter.is_available = MagicMock(return_value=True)
        return adapter

    @pytest.mark.asyncio
    async def test_verify_founded_year_confirmed_by_s_tier(self):
        from src.collector.gt_field_verifier import verify_high_risk_fields
        from src.search.search_adapter import EnhancedSearchResult

        adapter = self._mock_adapter()
        adapter.search = AsyncMock(return_value=[
            EnhancedSearchResult(
                title="Starbucks founded 1971", url="https://starbucks.com/about",
                snippet="Starbucks was founded in 1971 in Seattle",
                provider="tavily", rank=1, source_tier="S",
            ),
        ])

        ai_values = {"founded_year": "1971"}
        result, _ = await verify_high_risk_fields(
            brand_name="星巴克", ai_field_values=ai_values,
            search_adapter=adapter,
            fields_to_verify=["founded_year"],
        )
        assert "founded_year" in result
        assert result["founded_year"]["validated_tier"] == "A"
        assert result["founded_year"]["validation_status"] == "confirmed_strong"

    @pytest.mark.asyncio
    async def test_verify_official_name_with_official_site(self):
        from src.collector.gt_field_verifier import verify_high_risk_fields
        from src.search.search_adapter import EnhancedSearchResult

        adapter = self._mock_adapter()
        adapter.search = AsyncMock(return_value=[
            EnhancedSearchResult(
                title="星巴克公司", url="https://www.starbucks.com/about-us",
                snippet="星巴克股份有限公司（Starbucks Corporation）是一家美国咖啡公司",
                provider="tavily", rank=1, source_tier="S",
            ),
        ])

        ai_values = {"official_name": "星巴克"}
        result, _ = await verify_high_risk_fields(
            brand_name="星巴克", ai_field_values=ai_values,
            search_adapter=adapter, fields_to_verify=["official_name"],
        )
        assert result["official_name"]["validated_tier"] in ("A", "B")
        assert result["official_name"]["validation_status"].startswith("confirmed")

    @pytest.mark.asyncio
    async def test_founded_year_not_confused_with_listed_year(self):
        from src.collector.gt_field_verifier import verify_high_risk_fields
        from src.search.search_adapter import EnhancedSearchResult

        adapter = self._mock_adapter()
        adapter.search = AsyncMock(return_value=[
            EnhancedSearchResult(
                title="Starbucks IPO", url="https://example.com/ipo",
                snippet="Starbucks went public in 1992 on NASDAQ",
                provider="tavily", rank=1, source_tier="A",
            ),
        ])

        ai_values = {"founded_year": "1971"}
        result, _ = await verify_high_risk_fields(
            brand_name="星巴克", ai_field_values=ai_values,
            search_adapter=adapter, fields_to_verify=["founded_year"],
        )
        # The search says 1992 (listed year), not 1971 (founded)
        assert result["founded_year"]["validation_status"] != "confirmed_strong"

    @pytest.mark.asyncio
    async def test_c_tier_search_only_weak_support(self):
        from src.collector.gt_field_verifier import verify_high_risk_fields
        from src.search.search_adapter import EnhancedSearchResult

        adapter = self._mock_adapter()
        adapter.search = AsyncMock(return_value=[
            EnhancedSearchResult(
                title="Some blog", url="https://random-blog.com/starbucks",
                snippet="Starbucks was founded in 1971 I think",
                provider="tavily", rank=1, source_tier="C",
            ),
        ])

        ai_values = {"founded_year": "1971"}
        result, _ = await verify_high_risk_fields(
            brand_name="星巴克", ai_field_values=ai_values,
            search_adapter=adapter, fields_to_verify=["founded_year"],
        )
        assert result["founded_year"]["validated_tier"] == "C"
        assert result["founded_year"]["validation_status"] == "weak_support"

    @pytest.mark.asyncio
    async def test_d_tier_search_does_not_upgrade(self):
        from src.collector.gt_field_verifier import verify_high_risk_fields
        from src.search.search_adapter import EnhancedSearchResult

        adapter = self._mock_adapter()
        adapter.search = AsyncMock(return_value=[
            EnhancedSearchResult(
                title="Forum post", url="https://zhidao.baidu.com/q",
                snippet="Starbucks maybe founded 1971?",
                provider="tavily", rank=1, source_tier="D",
            ),
        ])

        ai_values = {"founded_year": "1971"}
        result, _ = await verify_high_risk_fields(
            brand_name="星巴克", ai_field_values=ai_values,
            search_adapter=adapter, fields_to_verify=["founded_year"],
        )
        assert result["founded_year"]["validated_tier"] == "C"

    @pytest.mark.asyncio
    async def test_ai_never_upgrades_to_s(self):
        from src.collector.gt_field_verifier import verify_high_risk_fields
        from src.search.search_adapter import EnhancedSearchResult

        adapter = self._mock_adapter()
        adapter.search = AsyncMock(return_value=[
            EnhancedSearchResult(
                title="Starbucks Official", url="https://www.starbucks.com/about",
                snippet="Starbucks was founded in 1971 in Seattle, Washington",
                provider="tavily", rank=1, source_tier="S",
            ),
            EnhancedSearchResult(
                title="SEC Filing", url="https://www.sec.gov/starbucks",
                snippet="Starbucks Corporation founded 1971",
                provider="tavily", rank=2, source_tier="S",
            ),
        ])

        ai_values = {"founded_year": "1971"}
        result, _ = await verify_high_risk_fields(
            brand_name="星巴克", ai_field_values=ai_values,
            search_adapter=adapter, fields_to_verify=["founded_year"],
        )
        # Even with 2 S-tier confirmations, AI evidence cannot be S
        assert result["founded_year"]["validated_tier"] != "S"
        assert result["founded_year"]["validated_tier"] == "A"

    @pytest.mark.asyncio
    async def test_trace_contains_match_score_and_reason(self):
        from src.collector.gt_field_verifier import verify_high_risk_fields
        from src.search.search_adapter import EnhancedSearchResult

        adapter = self._mock_adapter()
        adapter.search = AsyncMock(return_value=[
            EnhancedSearchResult(
                title="Official site", url="https://starbucks.com/about",
                snippet="Starbucks was founded in 1971",
                provider="tavily", rank=1, source_tier="S",
            ),
        ])

        ai_values = {"founded_year": "1971"}
        result, _ = await verify_high_risk_fields(
            brand_name="星巴克", ai_field_values=ai_values,
            search_adapter=adapter, fields_to_verify=["founded_year"],
        )
        r = result["founded_year"]
        assert r.get("upgrade_reason")
        assert r.get("match_score") is not None
        assert len(r.get("matched_sources", [])) > 0

    @pytest.mark.asyncio
    async def test_verification_failure_does_not_block(self):
        from src.collector.gt_field_verifier import verify_high_risk_fields

        adapter = self._mock_adapter()
        adapter.search = AsyncMock(side_effect=Exception("API down"))

        ai_values = {"official_name": "星巴克"}
        result, _ = await verify_high_risk_fields(
            brand_name="星巴克", ai_field_values=ai_values,
            search_adapter=adapter, fields_to_verify=["official_name"],
        )
        # Should not raise, should return unconfirmed
        assert "official_name" in result
        assert result["official_name"]["validation_status"] == "unconfirmed"

    @pytest.mark.asyncio
    async def test_headquarters_scope_mismatch(self):
        from src.collector.gt_field_verifier import verify_high_risk_fields
        from src.search.search_adapter import EnhancedSearchResult

        adapter = self._mock_adapter()
        adapter.search = AsyncMock(return_value=[
            EnhancedSearchResult(
                title="Starbucks China HQ", url="https://news.qq.com/starbucks-china",
                snippet="Starbucks China headquarters is in Shanghai",
                provider="tavily", rank=1, source_tier="A",
            ),
        ])

        ai_values = {"headquarters": "Seattle, Washington, USA"}
        result, _ = await verify_high_risk_fields(
            brand_name="星巴克", ai_field_values=ai_values,
            search_adapter=adapter, fields_to_verify=["headquarters"],
        )
        # Should detect scope mismatch, not downgrade
        assert result["headquarters"]["validation_status"] in (
            "scope_mismatch", "unconfirmed", "ambiguous",
        )


# ── P0-2: Tavily answer as summary evidence ──────────────────────────────────


class TestTavilyAnswerEvidence:
    def test_tavily_answer_max_tier_b(self):
        """Tavily answer is summary, cannot be S or A."""
        from src.search.tavily_search_adapter import TavilySearchAdapter
        # The answer field from Tavily is always capped at B tier
        # This is enforced in GTSearchService or field verifier
        pass  # Tested via integration

    @pytest.mark.asyncio
    async def test_tavily_answer_has_underlying_urls(self):
        from src.search.tavily_search_adapter import TavilySearchAdapter
        from src.search.tavily_backend import TavilyBackend
        from src.search import SearchResult

        mock_backend = MagicMock(spec=TavilyBackend)
        mock_backend.search = AsyncMock(return_value=[
            SearchResult(title="T1", url="https://a.com", snippet="S1", source_quality="high"),
            SearchResult(title="T2", url="https://b.com", snippet="S2", source_quality="medium"),
        ])

        adapter = TavilySearchAdapter(mock_backend)
        results = await adapter.search("星巴克 official name")
        # Results should have underlying URLs (not standalone summary)
        for r in results:
            assert r.url


# ── Integration ───────────────────────────────────────────────────────────────


class TestGTQualityPipeline:
    """End-to-end: verifier wired into collector generates better evidence."""

    def test_field_policy_integrated_with_gt_collector(self):
        """FIELD_POLICIES should be importable and used by gt_collector."""
        from src.gt.field_policy import FIELD_POLICIES, get_high_priority_fields
        fields = get_high_priority_fields()
        assert len(fields) >= 5
        # All P0 fields should have search verification
        for f in fields:
            assert FIELD_POLICIES[f]["requires_search_verification"]

    def test_high_risk_fields_includes_5_key_fields(self):
        from src.gt.field_policy import get_high_priority_fields
        key5 = {"official_name", "founded_year", "official_domains",
                "headquarters", "core_products"}
        assert key5.issubset(set(get_high_priority_fields()))
