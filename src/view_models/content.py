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


async def build_content_detail_vm(brand, package_id: str, user, db) -> dict:
    """Build view model for content package detail page."""
    cp = (await db.execute(
        select(ContentPackage).where(
            ContentPackage.id == package_id,
            ContentPackage.brand_id == brand.id,
        )
    )).scalar_one_or_none()

    if not cp:
        return {"error": "not_found"}

    transitions = CONTENT_PACKAGE_TRANSITIONS.get(cp.status, [])
    fact_check = cp.fact_check_report or {}
    checklist = cp.publish_checklist or []

    can_edit = user.role in ("admin", "content_editor", "legal_reviewer")
    can_publish = can_edit and cp.status in ("approved", "fact_checked", "ready")

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "package": {
            "id": str(cp.id),
            "status": cp.status,
            "risk_level": cp.risk_level or "low",
            "content_type": cp.content_type or "",
            "created_at": cp.created_at.isoformat() if cp.created_at else "",
            "updated_at": cp.updated_at.isoformat() if cp.updated_at else "",
        },
        "content_items": cp.content_items or [],
        "schema_items": cp.schema_items or [],
        "fact_check": {
            "has_report": bool(fact_check),
            "claims_total": fact_check.get("total", 0),
            "supported": fact_check.get("supported", 0),
            "unsupported": fact_check.get("unsupported", 0),
            "contradicted": fact_check.get("contradicted", 0),
            "not_checkable": fact_check.get("not_checkable", 0),
            "high_risk": fact_check.get("high_risk_claims", []),
        },
        "checklist": [{"label": item.get("label", item) if isinstance(item, dict) else str(item),
                       "status": item.get("status", "pending") if isinstance(item, dict) else "pending"}
                      for item in checklist],
        "transitions": transitions,
        "permissions": {
            "can_edit": can_edit,
            "can_publish": can_publish,
            "can_fact_check": user.role in ("admin", "gt_reviewer", "analyst"),
            "can_transition": can_edit and len(transitions) > 0,
        },
    }
