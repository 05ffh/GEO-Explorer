"""P1-8: Reclassification ViewModel — list + detail + diff for historical re-attribution."""
from sqlalchemy import select, desc, func
from src.models.reclassification_run import ReclassificationRun

STATUS_LABELS = {
    "queued": "排队中", "running": "运行中", "completed": "已完成",
    "partial_failed": "部分失败", "failed": "失败", "cancelled": "已取消",
}
STATUS_COLORS = {
    "queued": "blue", "running": "amber", "completed": "green",
    "partial_failed": "amber", "failed": "red", "cancelled": "gray",
}


async def build_list_vm(brand, filters: dict, user, db) -> dict:
    """Build view model for /brands/{id}/reclassifications list page."""
    status_filter = filters.get("status", "")
    dry_run_filter = filters.get("dry_run", "")
    page = int(filters.get("page", 1))
    page_size = int(filters.get("page_size", 20))

    q = select(ReclassificationRun).where(
        ReclassificationRun.brand_id == brand.id,
        ReclassificationRun.organization_id == user.organization_id,
    ).order_by(desc(ReclassificationRun.created_at))

    if status_filter:
        q = q.where(ReclassificationRun.status == status_filter)
    if dry_run_filter == "true":
        q = q.where(ReclassificationRun.dry_run == True)
    elif dry_run_filter == "false":
        q = q.where(ReclassificationRun.dry_run == False)

    # Count total
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    batches = []
    for b in rows:
        changes = b.classification_changes_json or {}
        batches.append({
            "id": str(b.id),
            "status": b.status,
            "status_label": STATUS_LABELS.get(b.status, b.status),
            "status_color": STATUS_COLORS.get(b.status, "gray"),
            "dry_run": b.dry_run,
            "mode_label": "Dry Run" if b.dry_run else "正式写入",
            "from_date": str(b.from_date)[:10] if b.from_date else None,
            "to_date": str(b.to_date)[:10] if b.to_date else None,
            "eligible_runs_count": b.eligible_runs_count,
            "runs_processed": b.runs_processed,
            "runs_failed": b.runs_failed,
            "query_results_processed": b.query_results_processed,
            "hallucination_results_created": b.hallucination_results_created,
            "classification_changes": changes,
            "classification_changes_total": sum(changes.values()) if changes else 0,
            "reason": b.reason or "",
            "started_at": str(b.started_at)[:19] if b.started_at else None,
            "completed_at": str(b.completed_at)[:19] if b.completed_at else None,
            "can_view_detail": True,
            "can_view_diff": b.status == "completed",
            "can_apply": b.status == "completed" and b.dry_run,
            "can_cancel": b.status in ("queued", "running"),
            "can_generate_report": b.status == "completed" and not b.dry_run,
        })

    is_admin = user.role in ("admin", "owner") or user.platform_role in ("system_admin", "system_owner")
    can_dry_run = user.role in ("admin", "owner", "analyst") or user.platform_role in ("system_admin", "system_owner")
    can_apply = is_admin

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "batches": batches,
        "pagination": {"page": page, "page_size": page_size, "total": total},
        "filters": {
            "status": status_filter, "dry_run": dry_run_filter,
            "statuses": ["queued", "running", "completed", "partial_failed", "failed", "cancelled"],
        },
        "permissions": {
            "can_view": True,
            "can_dry_run": can_dry_run,
            "can_apply": can_apply,
            "can_cancel": is_admin,
            "disabled_reason": None if can_dry_run else "需要品牌管理员权限",
        },
    }


async def build_detail_vm(batch_id: str, brand, user, db) -> dict:
    """Build view model for /brands/{id}/reclassifications/{batch_id} detail page."""
    batch = (await db.execute(
        select(ReclassificationRun).where(
            ReclassificationRun.id == batch_id,
            ReclassificationRun.brand_id == brand.id,
        )
    )).scalar_one_or_none()

    if not batch:
        return {"error": "not_found"}

    changes = batch.classification_changes_json or {}
    progress = batch.progress_json or {}
    errors = batch.error_summary_json or {}
    sample_diffs = batch.sample_diffs_json or {}

    total_eligible = batch.eligible_runs_count or 1
    processed = batch.runs_processed or 0
    pct = int(processed / total_eligible * 100) if total_eligible > 0 else 0

    is_admin = user.role in ("admin", "owner") or user.platform_role in ("system_admin", "system_owner")

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "batch": {
            "id": str(batch.id),
            "status": batch.status,
            "status_label": STATUS_LABELS.get(batch.status, batch.status),
            "status_color": STATUS_COLORS.get(batch.status, "gray"),
            "dry_run": batch.dry_run,
            "mode_label": "Dry Run" if batch.dry_run else "正式写入",
            "reason": batch.reason or "",
            "from_date": str(batch.from_date)[:10] if batch.from_date else None,
            "to_date": str(batch.to_date)[:10] if batch.to_date else None,
            "detector_version": batch.detector_version,
            "gt_version_strategy": batch.gt_version_strategy,
            "quality_schema_version": batch.quality_schema_version,
            "started_at": str(batch.started_at)[:19] if batch.started_at else None,
            "completed_at": str(batch.completed_at)[:19] if batch.completed_at else None,
        },
        "progress": {
            "percentage": pct,
            "eligible_runs_count": batch.eligible_runs_count,
            "runs_processed": processed,
            "runs_failed": batch.runs_failed or 0,
            "query_results_processed": batch.query_results_processed or 0,
            "hallucination_results_created": batch.hallucination_results_created or 0,
        },
        "classification_changes": changes,
        "changes_total": sum(changes.values()) if changes else 0,
        "error_summary": errors,
        "diff_summary": {
            "sample_count": len(sample_diffs.get("items", []) if isinstance(sample_diffs, dict) else 0),
        },
        "report_artifacts": {
            "original_reports": [],
            "corrected_reports": [],
        },
        "actions": {
            "can_cancel": batch.status in ("queued", "running") and is_admin,
            "can_apply": batch.status == "completed" and batch.dry_run and is_admin,
            "can_generate_report": batch.status == "completed" and not batch.dry_run,
            "can_view_diff": batch.status == "completed",
            "is_polling": batch.status in ("queued", "running"),
        },
    }


async def build_diff_vm(batch_id: str, brand, filters: dict, user, db) -> dict:
    """Build view model for diff display."""
    batch = (await db.execute(
        select(ReclassificationRun).where(
            ReclassificationRun.id == batch_id,
            ReclassificationRun.brand_id == brand.id,
        )
    )).scalar_one_or_none()

    if not batch:
        return {"error": "not_found"}

    sample_diffs = batch.sample_diffs_json or {}
    diffs = sample_diffs.get("items", []) if isinstance(sample_diffs, dict) else []

    # Apply filters
    old_verdict_filter = filters.get("old_verdict", "")
    new_category_filter = filters.get("category", "")
    if old_verdict_filter:
        diffs = [d for d in diffs if d.get("old_verdict", "") == old_verdict_filter]
    if new_category_filter:
        diffs = [d for d in diffs if d.get("new_layer", "") == new_category_filter]

    page = int(filters.get("page", 1))
    page_size = int(filters.get("page_size", 20))
    total = len(diffs)
    start = (page - 1) * page_size
    diffs = diffs[start:start + page_size]

    # Diff summary
    changes = batch.classification_changes_json or {}
    old_incorrect = sum(1 for d in diffs if d.get("old_verdict") == "incorrect")
    to_contradicted = sum(1 for d in diffs if d.get("new_layer") == "ai_hallucination")

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "batch_id": str(batch.id),
        "diffs": diffs,
        "pagination": {"page": page, "page_size": page_size, "total": total},
        "summary": {
            "total_changes": sum(changes.values()) if changes else 0,
            "old_incorrect_count": old_incorrect,
            "to_contradicted_count": to_contradicted,
            "classification_changes": changes,
        },
        "filters": {
            "old_verdict": old_verdict_filter,
            "category": new_category_filter,
        },
    }
