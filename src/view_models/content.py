"""P2-FRONTEND: Content management VM — real ContentPackage listing with status workflow."""
from sqlalchemy import select, desc
from src.models.content_package import ContentPackage, CONTENT_PACKAGE_TRANSITIONS


async def build_content_vm(brand, user, db) -> dict:
    pkgs = (await db.execute(
        select(ContentPackage).where(ContentPackage.brand_id == brand.id)
        .order_by(desc(ContentPackage.created_at)).limit(50)
    )).scalars().all()

    rows = []
    for cp in pkgs:
        transitions = CONTENT_PACKAGE_TRANSITIONS.get(cp.status, [])
        rows.append({
            "id": str(cp.id),
            "status": cp.status,
            "risk_level": cp.risk_level or "low",
            "content_count": len(cp.content_items or []),
            "schema_count": len(cp.schema_items or []),
            "has_fact_check": bool(cp.fact_check_report),
            "has_source_map": bool(cp.fact_source_map),
            "published_platform": cp.published_platform or "",
            "publish_summary": cp.publish_status_summary or "",
            "published_targets": cp.published_target_count or 0,
            "failed_targets": cp.failed_target_count or 0,
            "verified": cp.verified_at is not None,
            "transitions": transitions,
            "created_at": cp.created_at.isoformat() if cp.created_at else "",
        })

    counts = {}
    for s in ("draft","fact_checked","needs_review","approved","exported","published","verification_pending","verified"):
        counts[s] = sum(1 for r in rows if r["status"] == s)

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "packages": rows,
        "counts": counts,
        "total": len(rows),
        "permissions": {
            "can_publish": user.role in ("admin","content_editor","legal_reviewer"),
            "can_fact_check": user.role in ("admin","gt_reviewer","analyst"),
            "role": user.role,
        },
    }
