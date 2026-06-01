"""Tests for health score engine (P1-6)."""
from src.reports.health_score import (
    compute_health_score, DEFAULT_KPI_WEIGHTS, GRADE_THRESHOLDS,
)


def make_kpis(**overrides):
    """Helper to build a kpi list from default weights."""
    kpis = []
    for key, weight in DEFAULT_KPI_WEIGHTS.items():
        value = overrides.get(key, 0.70)
        kpis.append({"key": key, "value": value, "sample_size": 50})
    return kpis


class TestHealthScore:
    def test_all_good_returns_high_score(self):
        result = compute_health_score(make_kpis(), sample_size=100)
        assert result["score"] >= 70
        assert result["grade"] == "需关注"  # 70 is near boundary

    def test_low_kpis_return_low_score(self):
        kpis = make_kpis(sov=0.10, accuracy_rate=0.20, citation_rate=0.10,
                         completeness_rate=0.15, first_rec_rate=0.05)
        result = compute_health_score(kpis, sample_size=100)
        assert result["score"] < 40
        assert result["grade"] in ("需行动", "高风险")

    def test_missing_kpis_normalized(self):
        """Only 3 of 10 KPIs available — still produces a score."""
        kpis = [
            {"key": "accuracy_rate", "value": 0.80, "sample_size": 50},
            {"key": "sov", "value": 0.60, "sample_size": 50},
        ]
        result = compute_health_score(kpis, sample_size=50)
        assert result["score"] > 0

    def test_no_kpis_returns_zero(self):
        result = compute_health_score([], sample_size=0)
        assert result["score"] == 0

    def test_p0_hallucination_penalty(self):
        result = compute_health_score(make_kpis(), p0_hallucination_count=3, sample_size=100)
        assert result["risk_adjustments"]
        assert any(a["points"] < 0 for a in result["risk_adjustments"])

    def test_p0_penalty_capped(self):
        result = compute_health_score(make_kpis(), p0_hallucination_count=10, sample_size=100)
        penalty = sum(a["points"] for a in result["risk_adjustments"] if a["type"] == "p0_hallucination")
        assert penalty >= -15

    def test_low_citation_penalty(self):
        kpis = make_kpis(citation_rate=0.10)
        result = compute_health_score(kpis, citation_rate=0.10, sample_size=100)
        assert any(a["type"] == "low_citation" for a in result["risk_adjustments"])

    def test_confidence_low_on_small_sample(self):
        result = compute_health_score(make_kpis(), sample_size=10)
        assert result["confidence"] == "low"

    def test_confidence_low_on_many_missing(self):
        kpis = [{"key": "accuracy_rate", "value": 0.80, "sample_size": 50}]
        result = compute_health_score(kpis, sample_size=50)
        assert result["confidence"] in ("low", "medium")

    def test_normalized_weights_sum_to_one(self):
        """Available weights should normalize to 1.0."""
        kpis = make_kpis()
        result = compute_health_score(kpis, sample_size=100)
        total_weight = sum(b["weight"] for b in result["score_breakdown"])
        assert abs(total_weight - 1.0) < 0.01

    def test_breakdown_has_contributions(self):
        result = compute_health_score(make_kpis(), sample_size=100)
        assert len(result["score_breakdown"]) == len(DEFAULT_KPI_WEIGHTS)
        for b in result["score_breakdown"]:
            assert "kpi" in b
            assert "score" in b
            assert "weight" in b
            assert "contribution" in b
