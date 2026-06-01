"""Tests for benchmark engine (P2-1)."""
import pytest
from src.benchmark.engine import (
    KPI_KEYS, _percentile, _assess_quality, _make_benchmark_key,
    BENCHMARK_REQUIREMENTS,
)


class TestPercentile:
    def test_p50_median(self):
        vals = [0.1, 0.2, 0.3, 0.4, 0.5]
        assert _percentile(vals, 50) == 0.3

    def test_p25(self):
        vals = [0.0, 0.2, 0.4, 0.6, 0.8]
        assert _percentile(vals, 25) == 0.2

    def test_p75(self):
        vals = [0.0, 0.2, 0.4, 0.6, 0.8]
        assert _percentile(vals, 75) == 0.6

    def test_single_value(self):
        assert _percentile([0.5], 50) == 0.5

    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_extremes(self):
        vals = [0.1, 0.9]
        assert _percentile(vals, 0) == 0.1
        assert _percentile(vals, 100) == 0.9


class TestGapClassification:
    def test_none_gap(self):
        from src.benchmark.comparison import _classify_gap
        assert _classify_gap(0.02) == "none"

    def test_small_gap(self):
        from src.benchmark.comparison import _classify_gap
        assert _classify_gap(0.07) == "small"

    def test_moderate_gap(self):
        from src.benchmark.comparison import _classify_gap
        assert _classify_gap(0.15) == "moderate"

    def test_large_gap(self):
        from src.benchmark.comparison import _classify_gap
        assert _classify_gap(0.25) == "large"


class TestBenchmarkKey:
    def test_different_keys(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        k1 = _make_benchmark_key("finance", None, now, now)
        k2 = _make_benchmark_key("saas_b2b", None, now, now)
        assert k1 != k2

    def test_same_params_same_key(self):
        from datetime import datetime, timezone
        import uuid
        now = datetime.now(timezone.utc)
        k1 = _make_benchmark_key("finance", None, now, now)
        k2 = _make_benchmark_key("finance", None, now, now)
        assert k1 == k2


class TestQualityAssessment:
    def test_no_brands_insufficient(self):
        from src.models.benchmark_snapshot import BenchmarkSnapshot
        import uuid
        from datetime import datetime, timezone
        sn = BenchmarkSnapshot(
            benchmark_key="test", computed_at=datetime.now(timezone.utc),
            sample_brand_count=0,
        )
        sn = _assess_quality(sn, 10, BENCHMARK_REQUIREMENTS)
        assert sn.quality_level == "insufficient"

    def test_below_threshold_insufficient(self):
        from src.models.benchmark_snapshot import BenchmarkSnapshot
        from datetime import datetime, timezone
        sn = BenchmarkSnapshot(
            benchmark_key="test2", computed_at=datetime.now(timezone.utc),
            sample_brand_count=8,
        )
        sn = _assess_quality(sn, 10, BENCHMARK_REQUIREMENTS)
        assert sn.quality_level == "insufficient"


class TestKPIKeys:
    def test_all_kpis_present(self):
        required = {"sov", "accuracy_rate", "citation_rate", "first_rec_rate",
                     "completeness_rate", "scenario_recall", "semantic_stability",
                     "differentiation", "cross_platform_consistency", "recommendation_quality"}
        assert set(KPI_KEYS) == required


class TestDisplayDecision:
    def test_no_snapshot_hidden(self):
        from src.benchmark.display import can_display_benchmark
        result = can_display_benchmark(None, None)
        assert result.allowed is False
        assert result.display_mode == "hidden"

    def test_insufficient_quality_hidden(self):
        from src.models.benchmark_snapshot import BenchmarkSnapshot
        from datetime import datetime, timezone
        from src.benchmark.display import can_display_benchmark
        sn = BenchmarkSnapshot(
            benchmark_key="test", computed_at=datetime.now(timezone.utc),
            sample_brand_count=5, quality_level="insufficient",
            freshness_status="fresh",
        )
        result = can_display_benchmark(sn, None)
        assert result.allowed is False

    def test_stale_limited(self):
        from src.models.benchmark_snapshot import BenchmarkSnapshot
        from datetime import datetime, timezone
        from src.benchmark.display import can_display_benchmark
        sn = BenchmarkSnapshot(
            benchmark_key="test", computed_at=datetime.now(timezone.utc),
            sample_brand_count=20, quality_level="high",
            freshness_status="stale",
        )
        result = can_display_benchmark(sn, None)
        assert result.display_mode == "limited"

    def test_expired_hidden(self):
        from src.models.benchmark_snapshot import BenchmarkSnapshot
        from datetime import datetime, timezone
        from src.benchmark.display import can_display_benchmark
        sn = BenchmarkSnapshot(
            benchmark_key="test", computed_at=datetime.now(timezone.utc),
            sample_brand_count=20, quality_level="high",
            freshness_status="expired",
        )
        result = can_display_benchmark(sn, None)
        assert result.allowed is False
