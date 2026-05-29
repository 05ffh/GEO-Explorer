"""GEO Explorer — Dashboard ViewModel.

Pre-computes all display values for the brand overview page.
Templates only render — no business logic in Jinja2.
"""
from datetime import datetime, timezone

from sqlalchemy import select, desc, func
from src.models.collection_run import CollectionRun
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.ground_truth import GroundTruthVersion
from src.models.gt_candidate import GroundTruthCandidate
from src.models.hallucination import HallucinationResult
from src.models.action_theme import ActionTheme
from src.models.content_package import ContentPackage
from src.schemas.ground_truth import KPI_DISPLAY_NAMES


KPI_KEYS = [
    "sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate",
    "scenario_recall", "semantic_stability", "differentiation",
    "cross_platform_consistency", "recommendation_quality",
]


async def get_latest_completed_run(brand_id, db):
    """Get the most recent collection run with completed analysis."""
    result = await db.execute(
        select(CollectionRun).where(
            CollectionRun.brand_id == brand_id,
            CollectionRun.analysis_status == "completed",
        ).order_by(desc(CollectionRun.analysis_completed_at)).limit(1)
    )
    return result.scalar_one_or_none()


async def build_dashboard_vm(brand, user, db) -> dict:
    """Build view model for the brand overview dashboard page.

    Returns pre-computed display values: kpi_cards with display_value strings,
    health_score, blocking_issues, data_reliability, top_risks, priority_actions,
    recent_changes, and permissions.
    """
    latest_run = await get_latest_completed_run(brand.id, db)
    snapshot = None
    prev_snapshot = None

    if latest_run:
        snap_result = await db.execute(
            select(MetricsSnapshot).where(
                MetricsSnapshot.collection_run_id == latest_run.id,
                MetricsSnapshot.platform.is_(None),
                MetricsSnapshot.dimension.is_(None),
            ).limit(1)
        )
        snapshot = snap_result.scalar_one_or_none()

        # Previous run for trend comparison
        prev_run_result = await db.execute(
            select(CollectionRun).where(
                CollectionRun.brand_id == brand.id,
                CollectionRun.analysis_status == "completed",
                CollectionRun.analysis_completed_at < latest_run.analysis_completed_at,
            ).order_by(desc(CollectionRun.analysis_completed_at)).limit(1)
        )
        prev_run = prev_run_result.scalar_one_or_none()
        if prev_run:
            prev_snap_result = await db.execute(
                select(MetricsSnapshot).where(
                    MetricsSnapshot.collection_run_id == prev_run.id,
                    MetricsSnapshot.platform.is_(None),
                    MetricsSnapshot.dimension.is_(None),
                ).limit(1)
            )
            prev_snapshot = prev_snap_result.scalar_one_or_none()

    # Build KPI cards with pre-computed display values
    kpi_cards = []
    if snapshot:
        ek = (snapshot.details or {}).get("extended_kpis", {})
        kpi_raw = {
            "sov": snapshot.sov,
            "first_rec_rate": snapshot.first_rec_rate,
            "accuracy_rate": snapshot.accuracy_rate,
            "completeness_rate": snapshot.completeness_rate,
            "citation_rate": snapshot.citation_rate,
            "scenario_recall": ek.get("scenario_recall", {}).get("value", 0) if isinstance(ek.get("scenario_recall"), dict) else 0,
            "semantic_stability": ek.get("semantic_stability", {}).get("value", 0) if isinstance(ek.get("semantic_stability"), dict) else 0,
            "differentiation": ek.get("differentiation", {}).get("value", 0) if isinstance(ek.get("differentiation"), dict) else 0,
            "cross_platform_consistency": ek.get("cross_platform_consistency", {}).get("value", 0) if isinstance(ek.get("cross_platform_consistency"), dict) else 0,
            "recommendation_quality": ek.get("recommendation_quality", {}).get("value", 0) if isinstance(ek.get("recommendation_quality"), dict) else 0,
        }

        kpi_cards_raw = (snapshot.details or {}).get("kpi_cards", [])

        for key in KPI_KEYS:
            raw = kpi_raw.get(key, 0)
            is_pct = key in ("sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate")
            display_value = f"{round(raw * 100)}%" if is_pct else f"{round(raw, 1)}"

            card_detail = next((c for c in kpi_cards_raw if c.get("key") == key), {})
            numerator = card_detail.get("numerator")
            denominator = card_detail.get("denominator")
            confidence = card_detail.get("confidence", "medium")

            trend_display = None
            trend_direction = None
            if prev_snapshot and key in ("sov", "first_rec_rate", "accuracy_rate"):
                prev_val = getattr(prev_snapshot, key, 0)
                delta = raw - prev_val
                if abs(delta) > 0.001:
                    trend_display = f"{'+' if delta > 0 else ''}{round(delta * 100, 1)}%"
                    trend_direction = "up" if delta > 0 else "down"

            kpi_cards.append({
                "key": key,
                "brand_id": str(brand.id),
                "label": KPI_DISPLAY_NAMES.get(key, key),
                "display_value": display_value,
                "numerator": numerator,
                "denominator": denominator,
                "confidence": confidence,
                "confidence_label": confidence,
                "trend_display": trend_display,
                "trend_direction": trend_direction,
            })

    # Health score: average of core accuracy KPIs
    health_score = 0
    if kpi_cards:
        core = [c for c in kpi_cards if c["key"] in ("accuracy_rate", "completeness_rate", "citation_rate")]
        if core:
            health_score = sum(float(c["display_value"].replace("%", "")) for c in core) / len(core)
    health_label = "良好" if health_score >= 70 else ("一般" if health_score >= 40 else "需关注")

    # Active GT
    active_gt_result = await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand.id,
            GroundTruthVersion.status == "active",
        ).order_by(desc(GroundTruthVersion.version)).limit(1)
    )
    active_gt = active_gt_result.scalar_one_or_none()

    # Blocking issues
    blocking_issues = []
    if not active_gt:
        blocking_issues.append({
            "type": "gt_missing",
            "message": "GT 未 Promote，无法正式计算准确率",
            "link": f"/brands/{brand.id}/gt-review",
        })

    p0_count = (await db.execute(
        select(func.count(HallucinationResult.id)).where(
            HallucinationResult.brand_id == brand.id,
            HallucinationResult.severity == "P0",
            HallucinationResult.human_reviewed == False,  # noqa: E712
        )
    )).scalar()
    if p0_count > 0:
        blocking_issues.append({
            "type": "p0_unreviewed",
            "message": f"P0 幻觉 ({p0_count}条) 未复核",
            "link": f"/brands/{brand.id}/hallucinations",
        })

    high_risk_pkgs = (await db.execute(
        select(func.count(ContentPackage.id)).where(
            ContentPackage.brand_id == brand.id,
            ContentPackage.risk_level == "high",
            ContentPackage.status == "needs_review",
        )
    )).scalar()
    if high_risk_pkgs > 0:
        blocking_issues.append({
            "type": "content_needs_review",
            "message": f"Content Package ({high_risk_pkgs}个) 高风险，需审核",
            "link": f"/brands/{brand.id}/content",
        })

    # Data reliability
    gt_coverage = active_gt.gt_coverage_rate if active_gt else 0
    pending_candidates = (await db.execute(
        select(func.count(GroundTruthCandidate.id)).where(
            GroundTruthCandidate.brand_id == brand.id,
            GroundTruthCandidate.status == "pending_review",
        )
    )).scalar()

    is_stale = False
    if latest_run and latest_run.analysis_completed_at:
        age_days = (datetime.now(timezone.utc) - latest_run.analysis_completed_at).days
        is_stale = age_days > 7

    is_partial = latest_run.failure_count > 0 if latest_run else False
    platform_success_rate = 0
    if latest_run and latest_run.total_queries > 0:
        platform_success_rate = int(latest_run.success_count / latest_run.total_queries * 100)

    data_reliability = {
        "active_gt": active_gt is not None,
        "gt_coverage": round(gt_coverage * 100),
        "pending_candidates": pending_candidates,
        "latest_snapshot_at": latest_run.analysis_completed_at.isoformat() if latest_run and latest_run.analysis_completed_at else None,
        "collection_run_id": str(latest_run.id) if latest_run else None,
        "is_stale": is_stale,
        "is_partial": is_partial,
        "platform_success_rate": platform_success_rate,
    }

    # Priority action themes
    themes_result = await db.execute(
        select(ActionTheme).where(
            ActionTheme.brand_id == brand.id,
            ActionTheme.status.in_(["detected", "confirmed"]),
        ).order_by(ActionTheme.priority.asc(), ActionTheme.created_at.desc()).limit(3)
    )
    themes = themes_result.scalars().all()

    priority_actions = [{
        "id": str(t.id),
        "title": t.title,
        "priority": t.priority,
        "status": t.status,
        "affected_fields": t.affected_fields or [],
    } for t in themes]

    # P1 hallucination count
    p1_count = (await db.execute(
        select(func.count(HallucinationResult.id)).where(
            HallucinationResult.brand_id == brand.id,
            HallucinationResult.severity == "P1",
            HallucinationResult.human_reviewed == False,  # noqa: E712
        )
    )).scalar()

    # Recent changes (trend deltas)
    recent_changes = {}
    if prev_snapshot and snapshot:
        for key in ("sov", "first_rec_rate", "accuracy_rate"):
            delta = getattr(snapshot, key, 0) - getattr(prev_snapshot, key, 0)
            if abs(delta) > 0.001:
                recent_changes[key] = {
                    "delta": round(delta * 100, 1),
                    "direction": "up" if delta > 0 else "down",
                    "label": KPI_DISPLAY_NAMES.get(key, key),
                }

    return {
        "brand": {"id": str(brand.id), "name": brand.name, "industry": brand.industry or ""},
        "has_data": snapshot is not None,
        "kpi_cards": kpi_cards,
        "health_score": round(health_score),
        "health_label": health_label,
        "blocking_issues": blocking_issues,
        "data_reliability": data_reliability,
        "top_risks": {
            "p0_hallucinations": p0_count,
            "p1_hallucinations": p1_count,
            "high_risk_content": high_risk_pkgs,
        },
        "priority_actions": priority_actions,
        "recent_changes": recent_changes,
        "permissions": {
            "can_trigger_collection": user.role in ("admin", "analyst"),
            "can_review_gt": user.role in ("admin", "gt_reviewer"),
            "can_confirm_hallucination": user.role in ("admin", "analyst", "gt_reviewer"),
            "can_generate_content": user.role in ("admin", "content_editor"),
            "can_approve_high_risk": user.role in ("admin", "legal_reviewer"),
        },
    }
