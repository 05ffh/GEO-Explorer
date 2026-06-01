"""Benchmark computation engine (P2-1). Industry KPI percentile aggregation."""
import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.metrics_snapshot import MetricsSnapshot
from src.models.collection_run import CollectionRun
from src.models.brand import Brand
from src.models.industry_template import IndustryTemplate
from src.models.benchmark_definition import BenchmarkDefinition
from src.models.benchmark_snapshot import BenchmarkSnapshot

logger = logging.getLogger(__name__)

BENCHMARK_REQUIREMENTS = {
    "min_brand_count_global": 10,
    "min_brand_count_org": 5,
    "min_run_count": 10,
    "min_success_rate": 0.70,
    "max_snapshot_age_days": 30,
    "min_platform_count": 2,
}

KPI_KEYS = [
    "sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate",
    "scenario_recall", "semantic_stability", "differentiation",
    "cross_platform_consistency", "recommendation_quality",
]


async def get_active_definition(db: AsyncSession) -> BenchmarkDefinition | None:
    result = await db.execute(
        select(BenchmarkDefinition).where(
            BenchmarkDefinition.is_active == True,
        ).order_by(BenchmarkDefinition.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def compute_industry_benchmark(
    industry_key: str,
    db: AsyncSession,
    definition: BenchmarkDefinition | None = None,
    org_id: uuid.UUID | None = None,
    period_days: int = 30,
) -> BenchmarkSnapshot:
    """Compute industry benchmark for a given industry key."""
    if definition is None:
        definition = await get_active_definition(db)

    reqs = definition.sample_requirements if definition else BENCHMARK_REQUIREMENTS
    now = datetime.now(timezone.utc)
    period_start = now - timedelta(days=period_days)
    scope = "org" if org_id else "global"
    min_brands = reqs.get(f"min_brand_count_{scope}", 10 if scope == "global" else 5)

    # Create snapshot record
    benchmark_key = _make_benchmark_key(industry_key, org_id, period_start, period_end=now)
    snapshot = BenchmarkSnapshot(
        industry_key=industry_key,
        organization_id=org_id,
        benchmark_scope=scope,
        period_start=period_start,
        period_end=now,
        aggregation_strategy=definition.aggregation_strategy if definition else "latest",
        benchmark_definition_id=definition.id if definition else None,
        benchmark_definition_version=definition.version if definition else None,
        definition_snapshot_json=_definition_snapshot(definition, reqs),
        benchmark_key=benchmark_key,
        version="1.0",
        status="computing",
        computed_at=now,
        freshness_status="fresh",
        valid_until=now + timedelta(days=reqs.get("fresh_ttl_days", 3)),
    )
    db.add(snapshot)
    await db.flush()

    try:
        # Find eligible brands
        eligible, excluded_data = await _get_eligible_brands(industry_key, org_id, db, reqs)
        snapshot.sample_brand_count = len(eligible)
        snapshot.excluded_brand_count = excluded_data["total"]
        snapshot.excluded_demo_count = excluded_data["demo"]
        snapshot.excluded_unconfirmed_industry_count = excluded_data["unconfirmed"]

        # Gather KPI values
        kpi_values = {k: [] for k in KPI_KEYS}
        run_count = 0
        for brand in eligible:
            ms = await _get_latest_metrics(brand["id"], db, reqs.get("max_snapshot_age_days", 30))
            if ms:
                run_count += 1
                for k in KPI_KEYS:
                    val = _get_kpi_value(ms, k)
                    if val is not None:
                        kpi_values[k].append(val)

        snapshot.sample_run_count = run_count

        # Compute percentiles
        snapshot.kpi_p50 = {}
        snapshot.kpi_p25 = {}
        snapshot.kpi_p75 = {}
        snapshot.kpi_mean = {}
        snapshot.kpi_sample_counts = {}
        snapshot.kpi_confidence_intervals = {}

        for k in KPI_KEYS:
            vals = sorted(kpi_values[k])
            n = len(vals)
            snapshot.kpi_sample_counts[k] = n
            if n >= 2:
                snapshot.kpi_p50[k] = _percentile(vals, 50)
                snapshot.kpi_p25[k] = _percentile(vals, 25)
                snapshot.kpi_p75[k] = _percentile(vals, 75)
                snapshot.kpi_mean[k] = sum(vals) / n
                # Simple CI: ±1.96 * std / sqrt(n) for 95%
                if n >= 4:
                    mean = snapshot.kpi_mean[k]
                    variance = sum((x - mean) ** 2 for x in vals) / (n - 1)
                    std_err = (variance ** 0.5) / (n ** 0.5)
                    ci_half = 1.96 * std_err
                    snapshot.kpi_confidence_intervals[k] = {
                        "ci_lower": max(0, mean - ci_half),
                        "ci_upper": min(1, mean + ci_half),
                        "margin_of_error": ci_half,
                    }

        # Quality assessment
        snapshot = _assess_quality(snapshot, min_brands, reqs)
        snapshot.status = "active"
        await db.flush()

        # Supersede old active snapshots for same key
        await db.execute(
            text("UPDATE benchmark_snapshots SET status='superseded', superseded_by_id=:new_id "
                 "WHERE benchmark_key=:key AND status='active' AND id != :new_id"),
            {"new_id": snapshot.id, "key": benchmark_key},
        )

        await db.commit()
        return snapshot

    except Exception as exc:
        snapshot.status = "failed"
        snapshot.error_message = str(exc)[:2000]
        await db.commit()
        logger.error(f"Benchmark computation failed for {industry_key}: {exc}")
        raise


async def _get_eligible_brands(industry_key, org_id, db, reqs) -> tuple[list[dict], dict]:
    excluded = {"total": 0, "demo": 0, "unconfirmed": 0, "test": 0}
    conditions = [Brand.industry == industry_key]
    if org_id:
        conditions.append(Brand.organization_id == org_id)

    result = await db.execute(select(Brand).where(and_(*conditions)))
    brands = result.scalars().all()

    eligible = []
    for b in brands:
        if getattr(b, "is_demo", False):
            excluded["demo"] += 1; excluded["total"] += 1; continue
        if getattr(b, "is_test", False):
            excluded["test"] += 1; excluded["total"] += 1; continue
        industry_confirmed = getattr(b, "industry_confidence", None)
        if industry_confirmed and industry_confirmed == "unknown":
            excluded["unconfirmed"] += 1; excluded["total"] += 1; continue
        eligible.append({"id": b.id, "name": b.name})
    return eligible, excluded


async def _get_latest_metrics(brand_id, db, max_age_days: int) -> MetricsSnapshot | None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    result = await db.execute(
        select(MetricsSnapshot).join(CollectionRun).where(
            MetricsSnapshot.brand_id == brand_id,
            CollectionRun.collection_status == "completed",
            MetricsSnapshot.created_at >= cutoff,
        ).order_by(MetricsSnapshot.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


def _get_kpi_value(ms: MetricsSnapshot, key: str) -> float | None:
    if key == "sov":
        return float(ms.sov) if ms.sov is not None else None
    if key == "first_rec_rate":
        return float(ms.first_rec_rate) if ms.first_rec_rate is not None else None
    if key == "accuracy_rate":
        return float(ms.accuracy_rate) if ms.accuracy_rate is not None else None
    if key == "completeness_rate":
        return float(ms.completeness_rate) if ms.completeness_rate is not None else None
    if key == "citation_rate":
        return float(ms.citation_rate) if ms.citation_rate is not None else None
    ek = (ms.details or {}).get("extended_kpis", {}) if hasattr(ms, 'details') else {}
    v = ek.get(key)
    if v is not None:
        return float(v.get("value", 0)) if isinstance(v, dict) else float(v)
    return None


def _percentile(sorted_vals: list[float], pct: int) -> float:
    """Linear interpolation percentile."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    k = (pct / 100.0) * (n - 1)
    f = int(k)
    c = k - f
    if f + 1 >= n:
        return sorted_vals[-1]
    return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])


def _assess_quality(snapshot: BenchmarkSnapshot, min_brands: int, reqs: dict) -> BenchmarkSnapshot:
    n = snapshot.sample_brand_count
    if n == 0:
        snapshot.quality_level = "insufficient"
        snapshot.confidence = "low"
        snapshot.confidence_reason = "无符合条件的品牌参与基准计算"
        return snapshot

    if n < min_brands:
        snapshot.quality_level = "insufficient"
        snapshot.confidence = "low"
        snapshot.confidence_reason = f"样本品牌数 {n} 低于最低要求 {min_brands}"
    elif n < min_brands * 1.5:
        snapshot.quality_level = "low"
        snapshot.confidence = "low"
        snapshot.confidence_reason = f"样本品牌数 {n} 刚刚达到最低要求，可信度有限"
    elif n >= min_brands * 3:
        snapshot.quality_level = "high"
        snapshot.confidence = "high"
        snapshot.confidence_reason = f"样本品牌数 {n}，数据充分，可信度高"
    else:
        snapshot.quality_level = "medium"
        snapshot.confidence = "medium"
        snapshot.confidence_reason = f"样本品牌数 {n}，数据量适中"
    return snapshot


def _make_benchmark_key(industry_key: str, org_id: uuid.UUID | None, period_start, period_end) -> str:
    raw = f"{industry_key}:{org_id or 'global'}:{period_start.isoformat()}:{period_end.isoformat()}:v1.0"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _definition_snapshot(definition, reqs) -> dict:
    if definition:
        return {
            "name": definition.name, "version": definition.version,
            "sample_requirements": definition.sample_requirements,
            "aggregation_strategy": definition.aggregation_strategy,
            "percentile_method": definition.percentile_method,
            "outlier_policy": definition.outlier_policy,
            "fallback_policy": definition.fallback_policy,
            "freshness_policy": definition.freshness_policy,
            "material_gap_threshold": definition.material_gap_threshold,
        }
    return {"sample_requirements": reqs, "note": "default requirements, no definition persisted"}
