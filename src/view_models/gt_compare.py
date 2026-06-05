"""GT Version Compare ViewModel — side-by-side diff of candidate vs active GT."""

from sqlalchemy import select
from src.models.gt_candidate import GroundTruthCandidate
from src.models.ground_truth import GroundTruthVersion
from src.schemas.ground_truth import FIELD_TO_RISK_LEVEL


async def build_gt_compare_vm(brand, user, db) -> dict:
    """Build view model for /brands/{id}/gt-compare page."""
    candidate = (await db.execute(
        select(GroundTruthCandidate).where(
            GroundTruthCandidate.brand_id == brand.id,
            GroundTruthCandidate.status == "pending_review",
        ).order_by(GroundTruthCandidate.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    active_gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand.id,
            GroundTruthVersion.status == "active",
        ).order_by(GroundTruthVersion.version.desc()).limit(1)
    )).scalar_one_or_none()

    candidate_fields = candidate.candidate_json if candidate else {}
    active_fields = active_gt.ground_truth_json if active_gt else {}

    all_field_names = sorted(set(list(candidate_fields.keys()) + list(active_fields.keys())))

    rows = []
    stats = {"added": 0, "changed": 0, "unchanged": 0, "removed": 0}

    for fname in all_field_names:
        old_val = str(active_fields.get(fname, ""))[:200] if fname in active_fields else None
        new_val = str(candidate_fields.get(fname, ""))[:200] if fname in candidate_fields else None
        risk = FIELD_TO_RISK_LEVEL.get(fname, "low")

        if old_val is None and new_val is not None:
            status = "added"
            stats["added"] += 1
        elif new_val is None and old_val is not None:
            status = "removed"
            stats["removed"] += 1
        elif old_val != new_val:
            status = "changed"
            stats["changed"] += 1
        else:
            status = "unchanged"
            stats["unchanged"] += 1

        rows.append({
            "field_name": fname,
            "old_value": old_val or "",
            "new_value": new_val or "",
            "status": status,
            "risk_level": risk,
        })

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "has_candidate": candidate is not None,
        "has_active_gt": active_gt is not None,
        "candidate_id": str(candidate.id) if candidate else None,
        "active_gt_version": active_gt.version if active_gt else 0,
        "fields": rows,
        "stats": stats,
        "total_fields": len(rows),
    }
