"""GEO Explorer — Hallucination Risk + Review Workbench ViewModel (P2-4)."""
from sqlalchemy import select, func
from src.models.hallucination import HallucinationResult
from src.models.hallucination_review_log import HallucinationReviewLog


def cluster_key(h: HallucinationResult, dimension: str = "") -> tuple:
    return (h.error_type or "unknown", h.severity, h.field_name, dimension or "")


async def build_hallucination_vm(brand, filters, user, db) -> dict:
    """Build view model for the review workbench page."""
    # Review queue stats
    pending_q = select(func.count(HallucinationResult.id)).where(
        HallucinationResult.brand_id == brand.id,
        HallucinationResult.needs_human_review == True,
        HallucinationResult.review_status == "pending",
    )
    pending = (await db.execute(pending_q)).scalar() or 0
    claimed_q = select(func.count(HallucinationResult.id)).where(
        HallucinationResult.brand_id == brand.id,
        HallucinationResult.needs_human_review == True,
        HallucinationResult.review_status == "claimed",
    )
    claimed = (await db.execute(claimed_q)).scalar() or 0
    completed_q = select(func.count(HallucinationResult.id)).where(
        HallucinationResult.brand_id == brand.id,
        HallucinationResult.human_reviewed == True,
        HallucinationResult.review_status == "completed",
    )
    completed = (await db.execute(completed_q)).scalar() or 0

    # Recent review items (pending + claimed, top 20)
    items_q = select(HallucinationResult).where(
        HallucinationResult.brand_id == brand.id,
        HallucinationResult.needs_human_review == True,
        HallucinationResult.review_status.in_(("pending", "claimed")),
    ).order_by(HallucinationResult.review_priority.desc()).limit(20)
    items = (await db.execute(items_q)).scalars().all()

    review_items = []
    for r in items:
        review_items.append({
            "id": str(r.id),
            "field_name": r.field_name,
            "ai_claim": (r.ai_claim or "")[:120],
            "verdict": r.verdict,
            "severity": r.severity,
            "claim_type": r.claim_type,
            "review_status": r.review_status,
            "review_priority": r.review_priority,
            "review_reason": r.review_reason,
            "ground_truth_value": r.ground_truth_value,
            "reason": r.reason,
            "evidence_strength": (
                r.evidence_consensus_json.get("evidence_strength_level", "")
                if r.evidence_consensus_json else ""
            ),
            "claimed": r.claimed_by is not None,
        })

    # Permissions
    can_review = user.role in ("admin", "analyst", "gt_reviewer", "hallucination_reviewer",
                               "senior_reviewer") \
                 or user.platform_role in ("system_owner", "system_admin")

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "review_queue": {
            "pending": pending,
            "claimed": claimed,
            "completed": completed,
            "items": review_items,
        },
        "filters": {
            "severities": ["P0", "P1", "P2", "Info"],
            "review_statuses": ["pending", "claimed", "completed", "skipped"],
            "priorities": ["high", "medium", "low"],
        },
        "permissions": {
            "can_review": can_review,
        },
        "clusters": [],
        "total": pending + claimed,
    }
