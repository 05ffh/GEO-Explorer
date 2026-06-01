"""Tests for customer language translation layer (P1-6)."""
from src.reports.customer_language import (
    KPI_CUSTOMER_LANGUAGE, get_kpi_verdict, TECH_TERM_REPLACEMENTS,
    FORBIDDEN_ABSOLUTE_TERMS, replace_terms_for_customer_language,
    contains_forbidden_terms, get_industry_language,
)


class TestKPILanguageMapping:
    def test_all_10_kpis_have_language(self):
        expected = {
            "sov", "first_rec_rate", "accuracy_rate", "completeness_rate",
            "citation_rate", "scenario_recall", "semantic_stability",
            "differentiation", "cross_platform_consistency", "recommendation_quality",
        }
        assert set(KPI_CUSTOMER_LANGUAGE.keys()) == expected

    def test_each_kpi_has_required_fields(self):
        for key, cfg in KPI_CUSTOMER_LANGUAGE.items():
            for field in ["label", "question", "good", "bad", "action"]:
                assert field in cfg, f"{key} missing {field}"

    def test_each_kpi_has_thresholds(self):
        for key, cfg in KPI_CUSTOMER_LANGUAGE.items():
            assert "verdict_threshold_good" in cfg
            assert "verdict_threshold_bad" in cfg


class TestKPIVerdict:
    def test_good_above_threshold(self):
        assert get_kpi_verdict("sov", 0.60) == "good"

    def test_warning_between_thresholds(self):
        assert get_kpi_verdict("sov", 0.40) == "warning"

    def test_bad_below_threshold(self):
        assert get_kpi_verdict("sov", 0.10) == "bad"

    def test_unknown_kpi_defaults_to_warning(self):
        assert get_kpi_verdict("nonexistent", 0.40) == "warning"


class TestTermReplacement:
    def test_replaces_technical_terms(self):
        text = "SOV 是 KPI 之一"
        result = replace_terms_for_customer_language(text, "executive", "strict")
        assert "SOV" not in result

    def test_skips_urls(self):
        text = "查看 https://example.com/SOV 了解更多"
        result = replace_terms_for_customer_language(text, "executive", "strict")
        assert "https://example.com/SOV" in result

    def test_skips_code_blocks(self):
        text = "```\nSOV = 0.5\n```"
        result = replace_terms_for_customer_language(text, "executive", "strict")
        assert "SOV" in result

    def test_strict_mode_removes_all(self):
        text = "SOV 和 hallucination 都很重要"
        result = replace_terms_for_customer_language(text, "executive", "strict")
        assert "SOV" not in result
        assert "hallucination" not in result

    def test_executive_uses_strict(self):
        text = "GT 中的 KPI 显示 SOV 较低"
        result = replace_terms_for_customer_language(text, "executive", "strict")
        for term in ["GT", "KPI", "SOV"]:
            assert term not in result

    def test_empty_text(self):
        assert replace_terms_for_customer_language("", "executive") == ""


class TestForbiddenTerms:
    def test_detects_absolute_promise(self):
        assert "一定" in contains_forbidden_terms("AI 一定会推荐")

    def test_no_forbidden_terms(self):
        assert contains_forbidden_terms("品牌表现良好") == []

    def test_multiple_forbidden(self):
        found = contains_forbidden_terms("一定保证永远")
        assert len(found) == 3


class TestIndustryLanguage:
    def test_finance_has_language(self):
        lang = get_industry_language("finance")
        assert lang["opening_frame"]
        assert lang["risk_focus"]
        assert lang["compliance_note"]

    def test_unknown_industry_fallback(self):
        lang = get_industry_language("nonexistent")
        assert lang["opening_frame"] == ""

    def test_none_fallback(self):
        lang = get_industry_language(None)
        assert lang["opening_frame"] == ""

    def test_all_15_industries_have_language(self):
        from src.reports.customer_language import INDUSTRY_REPORT_LANGUAGE
        assert len(INDUSTRY_REPORT_LANGUAGE) == 15
