"""Tests for trend analyzer (P2-2)."""
import pytest
from src.trends.analyzer import (
    resample_metric_series, compute_stability_score, detect_cliff_drops,
    detect_sustained_trend, analyze_platform_volatility, determine_change_scope,
    MIN_POINTS, _bucket_key,
)


class TestResample:
    def test_resample_weekly_median(self):
        snapshots = [
            {"week_start": "2026-05-04", "value": 0.5},
            {"week_start": "2026-05-04", "value": 0.7},
            {"week_start": "2026-05-11", "value": 0.6},
        ]
        result = resample_metric_series(snapshots, "weekly", "median")
        assert len(result) == 2
        assert result[0]["value"] == 0.6  # median of [0.5, 0.7]
        assert result[1]["value"] == 0.6

    def test_empty_series(self):
        assert resample_metric_series([], "weekly") == []

    def test_resample_monthly(self):
        snapshots = [{"date": "2026-05-15", "value": 0.5}, {"date": "2026-05-20", "value": 0.7}]
        result = resample_metric_series(snapshots, "monthly", "latest")
        assert len(result) == 1
        assert result[0]["value"] == 0.7

    def test_resample_daily(self):
        snapshots = [{"date": "2026-05-15", "value": 0.3}, {"date": "2026-05-16", "value": 0.4}]
        result = resample_metric_series(snapshots, "daily", "median")
        assert len(result) == 2


class TestStabilityScore:
    def test_stable_series(self):
        vals = [0.7, 0.72, 0.71, 0.7, 0.73, 0.71, 0.72, 0.7]
        result = compute_stability_score(vals)
        assert result["score"] >= 80
        assert result["grade"] == "稳定"

    def test_volatile_series(self):
        vals = [0.8, 0.3, 0.7, 0.2, 0.6, 0.1, 0.9, 0.4]
        result = compute_stability_score(vals)
        assert result["score"] < 80

    def test_with_cliff_penalty(self):
        vals = [0.7, 0.72, 0.71, 0.7, 0.73, 0.71]
        result = compute_stability_score(vals, cliff_count=2)
        assert result["components"]["cliff_penalty"] == 30

    def test_with_missing_penalty(self):
        vals = [0.7, 0.72, 0.71, 0.7, 0.73, 0.71]
        result = compute_stability_score(vals, missing_ratio=0.5)
        assert result["components"]["missing_penalty"] == 10

    def test_insufficient_data(self):
        result = compute_stability_score([0.5])
        assert result["grade"] == "数据不足"

    def test_score_returns_components(self):
        result = compute_stability_score([0.6, 0.62, 0.61, 0.63, 0.6, 0.64])
        assert "volatility_penalty" in result["components"]
        assert "cliff_penalty" in result["components"]

    def test_score_has_reason(self):
        result = compute_stability_score([0.5, 0.52, 0.51, 0.53, 0.54, 0.5])
        assert result["reason"]


class TestCliffDetection:
    def test_detects_cliff_with_all_three_conditions(self):
        # Stable sequence with dramatic crash: tight distribution, then huge drop
        vals = [0.80, 0.80, 0.79, 0.81, 0.80, 0.80, 0.81, 0.80, 0.10, 0.12]
        dates = [f"2026-05-{i:02d}" for i in range(1, 11)]
        # With 10 points, pre-drop mean≈0.80, std≈0.007, drop to 0.10 gives z≈-100
        cliffs = detect_cliff_drops(vals, dates)
        assert len(cliffs) >= 1

    def test_no_cliff_on_small_drop(self):
        vals = [0.7, 0.69, 0.68, 0.67]
        dates = [f"2026-05-{i:02d}" for i in range(1, 5)]
        cliffs = detect_cliff_drops(vals, dates)
        assert len(cliffs) == 0

    def test_no_cliff_on_increase(self):
        vals = [0.5, 0.55, 0.6, 0.7]
        dates = [f"2026-05-{i:02d}" for i in range(1, 5)]
        cliffs = detect_cliff_drops(vals, dates)
        assert len(cliffs) == 0

    def test_insufficient_data_skipped(self):
        vals = [0.7, 0.4]  # only 2 points
        cliffs = detect_cliff_drops(vals, ["2026-05-01", "2026-05-08"])
        assert len(cliffs) == 0

    def test_cliff_severity_warning_vs_critical(self):
        # Very stable then crash: 8 × 0.80, then 0.30, 0.32 — z≈-2.5
        vals = [0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.80, 0.30, 0.32]
        dates = [f"2026-05-{i:02d}" for i in range(1, 11)]
        cliffs = detect_cliff_drops(vals, dates)
        assert len(cliffs) >= 1
        if cliffs:
            assert cliffs[0]["severity"] == "critical"


class TestSustainedTrend:
    def test_sustained_improvement(self):
        vals = [0.3, 0.32, 0.34, 0.36, 0.38, 0.42]
        result = detect_sustained_trend(vals)
        assert result is not None
        assert result["direction"] == "改善"

    def test_sustained_decline(self):
        vals = [0.7, 0.65, 0.6, 0.55, 0.5, 0.45]
        result = detect_sustained_trend(vals)
        assert result is not None
        assert result["direction"] == "恶化"

    def test_oscillating_no_trend(self):
        vals = [0.5, 0.6, 0.5, 0.6, 0.5, 0.6]
        result = detect_sustained_trend(vals)
        assert result is None

    def test_short_series_skipped(self):
        vals = [0.3, 0.4]
        result = detect_sustained_trend(vals)
        assert result is None

    def test_small_slope_not_business_significant(self):
        vals = [0.50, 0.51, 0.52, 0.51, 0.52, 0.53]
        result = detect_sustained_trend(vals)
        # may be statistically significant but not business significant
        if result:
            assert result.get("business_significant") == False or result["overall_change"] < 0.08


class TestPlatformVolatility:
    def test_volatile_platform_detected(self):
        data = {
            "kimi": {"sov": [0.5, 0.6, 0.3, 0.7, 0.2, 0.8]},
            "deepseek": {"sov": [0.6, 0.62, 0.61, 0.63, 0.6, 0.64]},
        }
        result = analyze_platform_volatility(data)
        assert result["kimi"]["sov"]["is_volatile"] is True
        assert result["deepseek"]["sov"]["is_volatile"] is False

    def test_insufficient_data(self):
        data = {"kimi": {"sov": [0.5, 0.6]}}
        result = analyze_platform_volatility(data)
        assert result["kimi"]["sov"]["insufficient_data"] is True


class TestChangeScope:
    def test_platform_specific(self):
        result = determine_change_scope("b1", "sov", ["kimi"], {"changed": False}, {"changed": False})
        assert result == "platform_specific"

    def test_industry_wide(self):
        result = determine_change_scope("b1", "sov", ["kimi", "deepseek"],
                                         {"changed": True}, {"changed": True})
        assert result == "industry_wide"

    def test_brand_specific(self):
        result = determine_change_scope("b1", "sov", ["kimi", "deepseek"],
                                         {"changed": False}, {"changed": False})
        assert result == "brand_specific"


class TestBucketKey:
    def test_weekly_key(self):
        from datetime import date
        key = _bucket_key(date(2026, 5, 15), "weekly")
        assert "W" in key

    def test_monthly_key(self):
        from datetime import date
        key = _bucket_key(date(2026, 5, 15), "monthly")
        assert key == "2026-05"

    def test_daily_key(self):
        from datetime import date
        key = _bucket_key(date(2026, 5, 15), "daily")
        assert key == "2026-05-15"
