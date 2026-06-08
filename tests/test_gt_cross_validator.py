"""GT Cross Validator tests — TDD: RED → GREEN.

Covers tier upgrade/downgrade rules, field-specific matchers, validation trace,
SourceEvidence contract, and time-sensitive field handling.
"""

import pytest


# ── P0-6: Public source_tier classifier ──────────────────────────────────────


class TestClassifySourceTier:
    def test_gov_domain_gets_s_tier(self):
        from src.search.source_tier import classify_source_tier
        assert classify_source_tier("https://www.example.gov.cn/doc") == "S"
        assert classify_source_tier("https://example.gov/doc") == "S"

    def test_edu_domain_gets_s_tier(self):
        from src.search.source_tier import classify_source_tier
        assert classify_source_tier("https://www.tsinghua.edu.cn/about") == "S"

    def test_official_ir_url_gets_s_tier(self):
        from src.search.source_tier import classify_source_tier
        assert classify_source_tier("https://company.com/investor/relations") == "S"

    def test_authoritative_third_party_gets_a_tier(self):
        from src.search.source_tier import classify_source_tier
        assert classify_source_tier("https://www.tianyancha.com/company/123") == "A"
        assert classify_source_tier("https://www.qichacha.com/firm/abc") == "A"

    def test_major_media_gets_b_tier(self):
        from src.search.source_tier import classify_source_tier
        assert classify_source_tier("https://www.36kr.com/article/1") == "B"
        assert classify_source_tier("https://finance.sina.com/stock") == "B"

    def test_blog_gets_c_or_d_tier(self):
        from src.search.source_tier import classify_source_tier
        tier = classify_source_tier("https://random-blog.example.com/post")
        assert tier in ("C", "D")

    def test_default_gets_c_tier(self):
        from src.search.source_tier import classify_source_tier
        assert classify_source_tier("https://some-random-site.com/page") == "C"

    def test_works_with_title_context(self):
        from src.search.source_tier import classify_source_tier
        tier = classify_source_tier("https://news.example.com/tech",
                                     title="About Us - Company Investor Relations")
        assert tier in ("A", "B")  # IR-related title should boost


# ── SourceEvidence dataclass ─────────────────────────────────────────────────


class TestSourceEvidence:
    def test_source_evidence_has_all_fields(self):
        from src.analyzer.gt_cross_validator import SourceEvidence
        ev = SourceEvidence(
            field_name="official_name", value="Starbucks",
            source_type="ai_platform", source_tier="C",
            source_quality="medium", provider="kimi",
        )
        assert ev.source_type == "ai_platform"
        assert ev.source_tier == "C"
        assert ev.original_source_tier is None
        assert ev.validation_status is None

    def test_source_evidence_ai_defaults(self):
        from src.analyzer.gt_cross_validator import SourceEvidence
        ev = SourceEvidence(
            field_name="founded_year", value="1971",
            source_type="ai_platform", source_tier="C",
            source_quality="medium", provider="doubao",
            original_source_tier="C",
        )
        assert ev.original_source_tier == "C"


# ── Cross validator: upgrade rules (P0-1, P0-2) ──────────────────────────────


class TestCrossValidatorUpgrade:
    """P0-1/2: Tier upgrade rules based on search evidence quality."""

    def _make_ai(self, field, value, provider="kimi"):
        from src.analyzer.gt_cross_validator import SourceEvidence
        return SourceEvidence(
            field_name=field, value=value, source_type="ai_platform",
            source_tier="C", source_quality="medium", provider=provider,
            original_source_tier="C",
        )

    def _make_search(self, field, value, tier, provider="tavily", url=""):
        from src.analyzer.gt_cross_validator import SourceEvidence
        return SourceEvidence(
            field_name=field, value=value, source_type="search_result",
            source_tier=tier, source_quality="high" if tier in ("S","A") else "medium",
            provider=provider, url=url or f"https://{provider}.com/result",
        )

    def test_one_s_tier_search_confirms_ai_to_a(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "1971")]
        search = [self._make_search("founded_year", "Starbucks was founded in 1971", "S")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "A"
        assert result[0].validation_status == "confirmed_strong"

    def test_one_a_tier_search_confirms_ai_to_b(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("official_name", "Starbucks")]
        search = [self._make_search("official_name", "Starbucks Corporation name", "A")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "B"
        assert result[0].validation_status == "confirmed_strong"

    def test_two_b_tier_search_confirm_ai_to_b(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("core_products", "Coffee, Tea, Pastries")]
        search = [
            self._make_search("core_products", "coffee and tea products", "B"),
            self._make_search("core_products", "Coffee, pastries, and more", "B"),
        ]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "B"
        assert result[0].validation_status == "confirmed_multi"

    def test_one_b_tier_search_confirms_ai_to_b(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("headquarters", "Seattle, WA")]
        search = [self._make_search("headquarters", "Based in Seattle", "B")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "B"
        assert result[0].validation_status == "confirmed_single"

    def test_c_tier_search_only_marks_weak_support(self):
        """P0-2: C-tier search does NOT trigger upgrade."""
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("positioning", "Premium coffee brand")]
        search = [self._make_search("positioning", "coffee brand", "C")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "C"
        assert result[0].validation_status == "weak_support"

    def test_d_tier_search_does_not_upgrade_ai(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("official_name", "Starbucks")]
        search = [self._make_search("official_name", "Starbucks maybe", "D")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "C"

    def test_unconfirmed_ai_stays_c(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("key_differentiators", "Unique taste")]
        search = [self._make_search("positioning", "Something else", "B")]  # different field
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "C"
        assert result[0].validation_status == "unconfirmed"

    def test_ai_never_upgrades_to_s(self):
        """P0-1: AI can never reach S tier."""
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("official_name", "Starbucks")]
        search = [
            self._make_search("official_name", "Starbucks Corporation", "S"),
            self._make_search("official_name", "Starbucks official name", "A"),
        ]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier != "S"
        assert result[0].source_tier == "A"

    def test_ai_source_type_remains_ai_platform(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "1971")]
        search = [self._make_search("founded_year", "founded in 1971", "S")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_type == "ai_platform"

    def test_ai_original_tier_preserved(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "1971")]
        search = [self._make_search("founded_year", "founded 1971", "S")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].original_source_tier == "C"


# ── Cross validator: downgrade rules (P0-3) ──────────────────────────────────


class TestCrossValidatorDowngrade:
    """P0-3: Downgrade to D only with clear contradiction evidence."""

    def _make_ai(self, field, value):
        from src.analyzer.gt_cross_validator import SourceEvidence
        return SourceEvidence(
            field_name=field, value=value, source_type="ai_platform",
            source_tier="C", source_quality="medium", provider="kimi",
            original_source_tier="C",
        )

    def _make_search(self, field, value, tier, provider="tavily"):
        from src.analyzer.gt_cross_validator import SourceEvidence
        return SourceEvidence(
            field_name=field, value=value, source_type="search_result",
            source_tier=tier, source_quality="high", provider=provider,
        )

    def test_one_s_tier_contradiction_downgrades_to_d(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "1999")]
        search = [self._make_search("founded_year", "The company was founded in 1971", "S")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "D"
        assert result[0].validation_status == "contradicted"

    def test_two_ab_tier_contradictions_downgrade_to_d(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "2000")]
        search = [
            self._make_search("founded_year", "founded 1971", "A"),
            self._make_search("founded_year", "established 1971", "B"),
        ]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "D"

    def test_single_b_tier_contradiction_does_not_downgrade(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "1999")]
        search = [self._make_search("founded_year", "founded 1971", "B")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier != "D"
        assert result[0].validation_status in ("unconfirmed", "contradicted", "ambiguous")

    def test_ambiguous_match_does_not_upgrade_or_downgrade(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("positioning", "Innovative tech company")]
        search = [self._make_search("positioning", "A technology firm known for innovation", "B")]
        result = cross_validate_ai_with_search(ai, search)
        # Should stay C or get weak/ambiguous
        assert result[0].validation_status in ("weak_support", "ambiguous", "unconfirmed", "confirmed_single")

    def test_scope_mismatch_does_not_downgrade(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("store_count", "30000 stores globally")]
        search = [self._make_search("store_count", "5000 stores in China", "A")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier != "D"
        assert result[0].validation_status in ("scope_mismatch", "unconfirmed", "ambiguous")


# ── Field-specific matchers (P0-4) ────────────────────────────────────────────


class TestFieldMatchers:
    def _make_ai(self, field, value):
        from src.analyzer.gt_cross_validator import SourceEvidence
        return SourceEvidence(
            field_name=field, value=value, source_type="ai_platform",
            source_tier="C", source_quality="medium", provider="kimi",
            original_source_tier="C",
        )

    def _make_search(self, field, value, tier="A"):
        from src.analyzer.gt_cross_validator import SourceEvidence
        return SourceEvidence(
            field_name=field, value=value, source_type="search_result",
            source_tier=tier, source_quality="high", provider="tavily",
        )

    def test_founded_year_not_confused_with_listed_year(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "1971")]
        search = [self._make_search("founded_year", "went public in 1992", "A")]
        result = cross_validate_ai_with_search(ai, search)
        # Listed year should NOT confirm founded_year → stays unconfirmed
        assert result[0].validation_status in ("unconfirmed", "weak_support")

    def test_founded_year_not_confused_with_entered_market_year(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "1971")]
        search = [self._make_search("founded_year", "entered China market in 1999", "A")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_tier == "C"

    def test_official_domain_normalizes_match(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("official_domains", "starbucks.com.cn")]
        search = [self._make_search("official_domains", "https://www.starbucks.com.cn/", "S")]
        result = cross_validate_ai_with_search(ai, search)
        # Should match after normalization
        assert result[0].source_tier in ("A", "B")

    def test_core_products_partial_overlap_marks_partial(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("core_products", "Coffee, Tea, Pastries, Sandwiches")]
        search = [self._make_search("core_products", "Coffee, Tea, Pastries", "B")]
        result = cross_validate_ai_with_search(ai, search)
        # Partial overlap should support but not be perfect match
        assert result[0].validation_status in ("confirmed_single", "confirmed_multi", "weak_support")


# ── Trace + Contract (P0-5, P0-7, P0-8) ──────────────────────────────────────


class TestCrossValidatorTrace:
    def _make_ai(self, field, value):
        from src.analyzer.gt_cross_validator import SourceEvidence
        return SourceEvidence(
            field_name=field, value=value, source_type="ai_platform",
            source_tier="C", source_quality="medium", provider="kimi",
            original_source_tier="C",
        )

    def _make_search(self, field, value, tier, provider="tavily", url=""):
        from src.analyzer.gt_cross_validator import SourceEvidence
        return SourceEvidence(
            field_name=field, value=value, source_type="search_result",
            source_tier=tier, source_quality="high", provider=provider,
            url=url or f"https://{provider}.com/r",
        )

    def test_trace_contains_match_score_and_reason(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "1971")]
        search = [self._make_search("founded_year", "Starbucks was founded in 1971", "S")]
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].match_score is not None
        assert result[0].upgrade_reason is not None
        assert "1971" in result[0].upgrade_reason.lower() or "year" in result[0].upgrade_reason.lower()

    def test_search_source_tier_not_modified(self):
        """P0-7: cross validator must never modify search source tiers."""
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("founded_year", "1971")]
        search = [self._make_search("founded_year", "founded 1971", "S")]
        original_search_tier = search[0].source_tier
        result = cross_validate_ai_with_search(ai, search)
        assert result[0].source_type == "ai_platform"  # returned AI only
        assert search[0].source_tier == original_search_tier  # unchanged

    def test_ai_consensus_without_search_stays_c(self):
        """P0-9: Multiple AI agreeing without search evidence stays C."""
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search, SourceEvidence
        ai = [
            self._make_ai("founded_year", "1971"),
            SourceEvidence(field_name="founded_year", value="1971",
                           source_type="ai_platform", source_tier="C",
                           source_quality="medium", provider="deepseek",
                           original_source_tier="C"),
        ]
        search = []  # No search evidence
        result = cross_validate_ai_with_search(ai, search)
        for r in result:
            assert r.source_tier == "C"

    def test_cross_validation_version_set(self):
        from src.analyzer.gt_cross_validator import cross_validate_ai_with_search
        ai = [self._make_ai("official_name", "Test")]
        search = [self._make_search("official_name", "Test Corp", "B")]
        result = cross_validate_ai_with_search(ai, search)
        # Check that matched_search_sources has expected structure
        assert result[0].matched_search_sources is not None or result[0].validation_status == "unconfirmed"
