"""Tests for insight builder (P1-6)."""
from src.reports.insight_builder import (
    build_one_line_summary, select_top_risks, select_top_action,
    build_executive_narrative, build_customer_opening_narrative,
)


def make_context(health_score=65, health_grade="需关注", findings=None, kpis=None, actions=None):
    return {
        "brand": {"name": "TestBrand"},
        "health": {"score": health_score, "grade": health_grade},
        "kpis": kpis or [],
        "key_findings": findings or [],
        "actions": actions or [],
        "data_quality": {"platform_count": 4, "query_count": 40, "success_count": 38, "failure_count": 2},
        "industry": {},
    }


class TestOneLineSummary:
    def test_generates_non_empty(self):
        ctx = make_context()
        summary = build_one_line_summary(ctx)
        assert len(summary) > 0

    def test_mentions_brand_indirectly(self):
        ctx = make_context(health_score=82, health_grade="健康")
        summary = build_one_line_summary(ctx)
        assert "健康" in summary or "良好" in summary

    def test_low_score_mentions_attention(self):
        ctx = make_context(health_score=35, health_grade="高风险")
        summary = build_one_line_summary(ctx)
        assert "关注" in summary or "风险" in summary

    def test_no_technical_terms(self):
        ctx = make_context()
        summary = build_one_line_summary(ctx)
        assert "SOV" not in summary


class TestTopRisks:
    def test_returns_limited(self):
        findings = [
            {"title": "R1", "severity": "P0", "impact_kpis": ["a", "b"], "evidence_level": "high"},
            {"title": "R2", "severity": "P1", "impact_kpis": ["c"], "evidence_level": "medium"},
            {"title": "R3", "severity": "P2", "impact_kpis": ["d"], "evidence_level": "low"},
            {"title": "R4", "severity": "P2", "impact_kpis": ["e"], "evidence_level": "low"},
        ]
        ctx = make_context(findings=findings)
        result = select_top_risks(ctx, limit=3)
        assert len(result) == 3

    def test_p0_ranked_first(self):
        findings = [
            {"title": "Low", "severity": "P2", "impact_kpis": ["a"], "evidence_level": "low"},
            {"title": "High", "severity": "P0", "impact_kpis": ["a", "b", "c"], "evidence_level": "high"},
        ]
        ctx = make_context(findings=findings)
        result = select_top_risks(ctx, limit=2)
        assert result[0]["title"] == "High"


class TestTopAction:
    def test_returns_none_for_empty(self):
        ctx = make_context()
        assert select_top_action(ctx) is None

    def test_selects_p0_first(self):
        actions = [
            {"priority": "P2", "content_asset": "", "recheck_timing": "", "acceptance_criteria": ""},
            {"priority": "P0", "content_asset": "FAQ", "recheck_timing": "14天", "acceptance_criteria": "准确率提升"},
        ]
        ctx = make_context(actions=actions)
        result = select_top_action(ctx)
        assert result["priority"] == "P0"

    def test_prefers_concrete_asset(self):
        actions = [
            {"priority": "P1", "content_asset": "", "recheck_timing": "", "acceptance_criteria": ""},
            {"priority": "P1", "content_asset": "品牌定位 FAQ", "recheck_timing": "14天", "acceptance_criteria": "准确率>70%"},
        ]
        ctx = make_context(actions=actions)
        result = select_top_action(ctx)
        assert result["content_asset"]


class TestExecutiveNarrative:
    def test_returns_all_fields(self):
        ctx = make_context(findings=[
            {"title": "Risk", "severity": "P1", "impact_kpis": ["a"], "evidence_level": "medium"},
        ], actions=[
            {"priority": "P1", "content_asset": "FAQ", "recheck_timing": "14天", "acceptance_criteria": "OK"},
        ])
        result = build_executive_narrative(ctx)
        assert "one_line" in result
        assert "top_risks" in result
        assert "top_action" in result
        assert "data_note" in result


class TestCustomerOpening:
    def test_non_empty(self):
        ctx = make_context()
        opening = build_customer_opening_narrative(ctx)
        assert len(opening) > 0
