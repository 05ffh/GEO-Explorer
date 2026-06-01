"""Gap attribution — explains WHY a KPI gap exists between brand and competitors/benchmark (P2-1)."""
import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.metrics_snapshot import MetricsSnapshot
from src.models.benchmark_snapshot import BenchmarkSnapshot
from src.models.gap_attribution import GapAttributionResult as GapAttributionModel
from src.benchmark.engine import KPI_KEYS, _get_kpi_value
from src.benchmark.comparison import _classify_gap
from src.reports.customer_language import (
    KPI_CUSTOMER_LANGUAGE, replace_terms_for_customer_language,
)

logger = logging.getLogger(__name__)


async def attribute_kpi_gap(
    brand_id: uuid.UUID,
    org_id: uuid.UUID,
    kpi_key: str,
    benchmark_snapshot_id: uuid.UUID | None,
    competitor_set_id: uuid.UUID | None,
    metrics_snapshot_id: uuid.UUID | None,
    db: AsyncSession,
) -> dict:
    """Attribute a KPI gap between brand and competitors/benchmark.

    Returns structured result with likely_drivers, evidence_blocks, caveat.
    """
    now = datetime.now(timezone.utc)

    # Load data
    ms = None
    if metrics_snapshot_id:
        ms = await db.get(MetricsSnapshot, metrics_snapshot_id)
    else:
        from src.benchmark.engine import _get_latest_metrics as get_ms
        ms = await get_ms(brand_id, db, 30)

    brand_value = None
    if ms:
        brand_value = _get_kpi_value(ms, kpi_key)

    benchmark = None
    if benchmark_snapshot_id:
        benchmark = await db.get(BenchmarkSnapshot, benchmark_snapshot_id)

    # Get comparison data
    from src.benchmark.comparison import build_competitor_comparison
    comparison = await build_competitor_comparison(brand_id, org_id, db, competitor_set_id)

    # Build gap analysis
    competitor_avg = (comparison.get("kpi_direct_avg") or {}).get(kpi_key)
    industry_p50 = benchmark.kpi_p50.get(kpi_key) if benchmark and benchmark.kpi_p50 else None

    gap_magnitude = 0.0
    if brand_value is not None and competitor_avg is not None:
        gap_magnitude = brand_value - competitor_avg
    elif brand_value is not None and industry_p50 is not None:
        gap_magnitude = brand_value - industry_p50

    # Platform dimension
    by_platform = _gap_by_platform(brand_id, kpi_key, db)

    # Scenario dimension
    by_scenario = _gap_by_scenario(brand_id, kpi_key, db)

    # Evidence blocks
    evidence_blocks = _build_evidence_blocks(kpi_key, gap_magnitude, by_platform, by_scenario, comparison)

    # Likely drivers
    likely_drivers, counter_evidence = _build_drivers(kpi_key, evidence_blocks)

    # Caveat
    caveat = _build_caveat(gap_magnitude, comparison.get("data_quality", {}))

    # Confidence
    confidence = _assess_gap_confidence(comparison.get("data_quality", {}), benchmark)

    result = {
        "brand_id": str(brand_id),
        "benchmark_snapshot_id": str(benchmark_snapshot_id) if benchmark_snapshot_id else None,
        "competitor_set_id": str(competitor_set_id) if competitor_set_id else None,
        "kpi_key": kpi_key,
        "gap_magnitude": gap_magnitude,
        "gap_significance": _classify_gap(abs(gap_magnitude)),
        "by_platform": by_platform,
        "by_scenario": by_scenario,
        "likely_drivers": likely_drivers,
        "evidence_blocks": evidence_blocks,
        "counter_evidence": counter_evidence,
        "confidence": confidence["level"],
        "confidence_reason": confidence["reason"],
        "data_coverage": {
            "brand_queries": comparison.get("data_quality", {}).get("total_competitors", 0),
            "competitor_queries": comparison.get("data_quality", {}).get("with_data", 0),
        },
        "caveat": caveat,
        "generated_at": now.isoformat(),
    }

    # Persist
    try:
        persisted = GapAttributionModel(
            brand_id=brand_id,
            organization_id=org_id,
            benchmark_snapshot_id=benchmark_snapshot_id,
            competitor_set_id=competitor_set_id,
            competitor_set_version=1,
            metrics_snapshot_id=metrics_snapshot_id,
            kpi_key=kpi_key,
            gap_magnitude=gap_magnitude,
            gap_significance=_classify_gap(abs(gap_magnitude)),
            result_json=result,
            confidence=confidence["level"],
            status="active",
            generated_at=now,
        )
        db.add(persisted)
        await db.flush()
        result["id"] = str(persisted.id)

        # Stale old results
        await db.execute(
            text("UPDATE gap_attribution_results SET status='stale', stale_reason='newer result available' "
                 "WHERE brand_id=:bid AND kpi_key=:kpi AND status='active' AND id != :new_id"),
            {"bid": brand_id, "kpi": kpi_key, "new_id": persisted.id},
        )
        await db.commit()
    except Exception as exc:
        logger.warning(f"Failed to persist GapAttributionResult: {exc}")

    return result


def _gap_by_platform(brand_id, kpi_key, db) -> dict:
    """Estimate gap by platform from available query results."""
    return {}


def _gap_by_scenario(brand_id, kpi_key, db) -> dict:
    """Estimate gap by question scenario type."""
    return {}


def _build_evidence_blocks(kpi_key, gap_magnitude, by_platform, by_scenario, comparison) -> list[dict]:
    blocks = []
    cfg = KPI_CUSTOMER_LANGUAGE.get(kpi_key, {})
    label = cfg.get("label", kpi_key)

    if abs(gap_magnitude) < 0.01:
        blocks.append({
            "dimension": "overall",
            "label": f"{label}",
            "finding": "品牌与该指标在竞品中无明显差距",
            "confidence": "high",
        })
        return blocks

    direction = "领先" if gap_magnitude > 0 else "落后"
    competitor_count = comparison.get("competitor_count", 0)
    blocks.append({
        "dimension": "overall",
        "label": f"{label}",
        "brand_value": comparison.get("brand_kpis", {}).get(kpi_key),
        "competitor_avg": (comparison.get("kpi_direct_avg") or {}).get(kpi_key),
        "industry_p50": (comparison.get("benchmark") or {}).get("kpi_p50", {}).get(kpi_key) if comparison.get("benchmark") else None,
        "finding": f"品牌在「{label}」上{direction}于竞品均值",
        "sample_size": competitor_count,
        "confidence": "medium",
    })

    return blocks


def _build_drivers(kpi_key, evidence_blocks) -> tuple[list[str], list[str]]:
    cfg = KPI_CUSTOMER_LANGUAGE.get(kpi_key, {})
    label = cfg.get("label", kpi_key)
    drivers = []
    counter = []

    for eb in evidence_blocks:
        finding = eb.get("finding", "")
        if "落后" in finding:
            drivers.append(f"在「{label}」方面可能存在改进空间")
        elif "领先" in finding:
            counter.append(f"在「{label}」方面品牌表现较好")

    return (drivers or [f"建议关注「{label}」相关指标"]), counter


def _build_caveat(gap_magnitude, data_quality) -> str:
    parts = []
    parts.append("该判断基于当前采集样本")
    if abs(gap_magnitude) < 0.05:
        parts.append("差距较小，可能属于正常波动范围")
    parts.append("仍需通过后续内容发布和复测验证")
    return "，".join(parts)


def _assess_gap_confidence(data_quality, benchmark) -> dict:
    total = data_quality.get("total_competitors", 0)
    with_data = data_quality.get("with_data", 0)
    if total == 0:
        return {"level": "low", "reason": "无竞品数据"}
    if with_data < 2:
        return {"level": "low", "reason": "竞品数据不足"}
    if with_data >= 5 and benchmark and benchmark.quality_level in ("high", "medium"):
        return {"level": "high", "reason": "数据充分，基准可靠"}
    return {"level": "medium", "reason": "竞品数据有限，结论仅供参考"}
