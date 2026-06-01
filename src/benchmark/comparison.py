"""Competitor comparison — time-aligned multi-brand KPI comparison (P2-1)."""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.metrics_snapshot import MetricsSnapshot
from src.models.collection_run import CollectionRun
from src.models.competitor_set import CompetitorSet
from src.models.benchmark_snapshot import BenchmarkSnapshot
from src.benchmark.engine import KPI_KEYS, _get_latest_metrics, _get_kpi_value, _percentile
from src.benchmark.display import can_display_benchmark, DisplayDecision

logger = logging.getLogger(__name__)

MAX_SNAPSHOT_AGE_DAYS = 14
TIME_ALIGNMENT_STRATEGY = "loose"


async def build_competitor_comparison(
    brand_id: uuid.UUID,
    org_id: uuid.UUID,
    db: AsyncSession,
    competitor_set_id: uuid.UUID | None = None,
) -> dict:
    """Build time-aligned competitor comparison for a brand.

    Returns structured comparison with:
    - Brand KPI vs each competitor's KPI
    - Direct competitor avg / All competitor avg
    - Time-aligned snapshot data
    - Data quality notes
    """
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=MAX_SNAPSHOT_AGE_DAYS)

    # Get competitor set
    if competitor_set_id:
        cs = await db.get(CompetitorSet, competitor_set_id)
    else:
        result = await db.execute(
            select(CompetitorSet).where(
                CompetitorSet.brand_id == brand_id,
                CompetitorSet.is_active == True,
            ).order_by(CompetitorSet.updated_at.desc()).limit(1)
        )
        cs = result.scalar_one_or_none()

    competitor_brand_ids = cs.competitor_brand_ids if cs else []

    # Get brand's own latest metrics
    brand_metrics = await _get_latest_metrics(brand_id, db, MAX_SNAPSHOT_AGE_DAYS)
    brand_kpis = {}
    if brand_metrics:
        for k in KPI_KEYS:
            val = _get_kpi_value(brand_metrics, k)
            if val is not None:
                brand_kpis[k] = val

    # Get competitor metrics
    competitors = []
    excluded_competitors = []
    kpi_aggregates = {k: [] for k in KPI_KEYS}
    direct_aggregates = {k: [] for k in KPI_KEYS}

    for cid_str in competitor_brand_ids:
        try:
            cid = uuid.UUID(cid_str) if isinstance(cid_str, str) else cid_str
        except ValueError:
            continue

        from src.models.brand import Brand
        comp_brand = await db.get(Brand, cid)
        if not comp_brand:
            excluded_competitors.append({"id": cid_str, "reason": "品牌不存在"})
            continue

        ms = await _get_latest_metrics(cid, db, MAX_SNAPSHOT_AGE_DAYS)
        if not ms:
            excluded_competitors.append({"id": cid_str, "name": comp_brand.name, "reason": "无最近采集数据"})
            continue

        comp_kpis = {}
        for k in KPI_KEYS:
            val = _get_kpi_value(ms, k)
            if val is not None:
                comp_kpis[k] = val
                kpi_aggregates[k].append(val)
                direct_aggregates[k].append(val)  # default: all = direct for now

        competitors.append({
            "brand_id": str(cid),
            "brand_name": comp_brand.name,
            "kpis": comp_kpis,
            "snapshot_date": ms.created_at.isoformat() if ms.created_at else None,
            "snapshot_age_days": (now - ms.created_at).days if ms.created_at else None,
        })

    # Compute averages
    avg_kpis = {}
    for k in KPI_KEYS:
        vals = kpi_aggregates[k]
        avg_kpis[k] = sum(vals) / len(vals) if vals else None
    direct_avg = {}
    for k in KPI_KEYS:
        vals = direct_aggregates[k]
        direct_avg[k] = sum(vals) / len(vals) if vals else None

    # Get benchmark
    bench_result = await db.execute(
        select(BenchmarkSnapshot).where(
            BenchmarkSnapshot.industry_key == "general",
            BenchmarkSnapshot.status == "active",
            BenchmarkSnapshot.freshness_status != "expired",
        ).order_by(BenchmarkSnapshot.computed_at.desc()).limit(1)
    )
    benchmark = bench_result.scalar_one_or_none()

    benchmark_data = None
    if benchmark:
        display = can_display_benchmark(benchmark, None)
        if display.allowed:
            benchmark_data = {
                "snapshot_id": str(benchmark.id),
                "quality_level": benchmark.quality_level,
                "confidence": benchmark.confidence,
                "sample_brand_count": benchmark.sample_brand_count,
                "freshness_status": benchmark.freshness_status,
                "kpi_p50": benchmark.kpi_p50,
                "kpi_p25": benchmark.kpi_p25,
                "kpi_p75": benchmark.kpi_p75,
                "display_mode": display.display_mode,
                "caveat": display.reason,
            }

    # Build KPI gap table
    gap_table = []
    for k in KPI_KEYS:
        bv = brand_kpis.get(k)
        ca = direct_avg.get(k)
        bp50 = benchmark_data["kpi_p50"].get(k) if benchmark_data else None

        row = {
            "kpi_key": k,
            "brand_value": bv,
            "competitor_avg_direct": ca,
            "industry_p50": bp50,
        }
        # Gap significance
        if bv is not None and ca is not None:
            gap = bv - ca
            row["gap"] = gap
            row["gap_significance"] = _classify_gap(abs(gap))
        gap_table.append(row)

    return {
        "brand_id": str(brand_id),
        "brand_kpis": brand_kpis,
        "comparison_period": {
            "start": period_start.isoformat(),
            "end": now.isoformat(),
            "max_snapshot_age_days": MAX_SNAPSHOT_AGE_DAYS,
            "strategy": TIME_ALIGNMENT_STRATEGY,
        },
        "competitor_groups": {
            "direct": competitors,
            "all": competitors,
        },
        "competitor_count": len(competitors),
        "excluded_competitors": excluded_competitors,
        "kpi_avg": avg_kpis,
        "kpi_direct_avg": direct_avg,
        "kpi_gap_table": gap_table,
        "benchmark": benchmark_data,
        "data_quality": {
            "total_competitors": len(competitor_brand_ids),
            "with_data": len(competitors),
            "excluded": len(excluded_competitors),
            "excluded_reasons": [e["reason"] for e in excluded_competitors],
        },
    }


def _classify_gap(abs_gap: float) -> str:
    if abs_gap < 0.05:
        return "none"
    if abs_gap < 0.10:
        return "small"
    if abs_gap < 0.20:
        return "moderate"
    return "large"
