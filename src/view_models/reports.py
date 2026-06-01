"""Reports page ViewModel (P1-6)."""
from sqlalchemy import select, desc, and_
from src.models.report_artifact import ReportArtifact
from src.models.collection_run import CollectionRun


async def build_reports_vm(brand, user, db) -> dict:
    """Build view model for the report download page."""
    # Recent collection runs for this brand
    runs = (await db.execute(
        select(CollectionRun).where(
            CollectionRun.brand_id == brand.id,
            CollectionRun.organization_id == user.organization_id,
        ).order_by(desc(CollectionRun.created_at)).limit(10)
    )).scalars().all()

    # Existing report artifacts
    artifacts = (await db.execute(
        select(ReportArtifact).where(
            ReportArtifact.brand_id == brand.id,
            ReportArtifact.organization_id == user.organization_id,
        ).order_by(desc(ReportArtifact.created_at))
    )).scalars().all()

    # Group artifacts by collection_run_id + edition
    artifact_map = {}
    for a in artifacts:
        key = f"{a.collection_run_id}:{a.edition}"
        if key not in artifact_map:
            artifact_map[key] = []
        artifact_map[key].append({
            "id": str(a.id),
            "edition": a.edition,
            "format": a.format,
            "status": a.status,
            "file_path": a.file_path,
            "report_version": a.report_version,
            "quality_status": a.quality_status,
            "download_count": a.download_count,
            "generated_at": a.generated_at.isoformat() if a.generated_at else "",
            "error_message": a.error_message,
            "stale_reason": a.stale_reason,
        })

    # Build run list with artifact status
    run_list = []
    for run in runs:
        run_artifacts = {}
        for edition in ["executive", "implementation", "customer"]:
            key = f"{run.id}:{edition}"
            items = artifact_map.get(key, [])
            # Find best artifact per format
            formats = {}
            for item in items:
                fmt = item["format"]
                if fmt not in formats or item["report_version"] > formats[fmt]["report_version"]:
                    formats[fmt] = item
            status = "not_generated"
            if items:
                statuses = {a["status"] for a in items}
                if "generating" in statuses or "queued" in statuses:
                    status = "generating"
                elif "generated" in statuses:
                    status = "generated"
                elif "failed" in statuses:
                    status = "failed"
                elif "stale" in statuses:
                    status = "stale"
            run_artifacts[edition] = {"status": status, "formats": formats}

        run_list.append({
            "id": str(run.id),
            "trigger_type": run.trigger_type,
            "collection_status": run.collection_status,
            "created_at": run.created_at.isoformat() if run.created_at else "",
            "total_queries": run.total_queries,
            "success_count": run.success_count,
            "artifacts": run_artifacts,
        })

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "runs": run_list,
        "editions": [
            {"key": "executive", "label": "高管摘要", "desc": "CEO/CMO 一页概览"},
            {"key": "implementation", "label": "执行方案", "desc": "内容团队可执行清单"},
            {"key": "customer", "label": "客户报告", "desc": "完整诊断与解释"},
        ],
    }
