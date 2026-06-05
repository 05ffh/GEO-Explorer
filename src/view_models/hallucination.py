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

    # Skipped count
    skipped_q = select(func.count(HallucinationResult.id)).where(
        HallucinationResult.brand_id == brand.id,
        HallucinationResult.needs_human_review == True,
        HallucinationResult.review_status == "skipped",
    )
    skipped = (await db.execute(skipped_q)).scalar() or 0

    # Feedback pending count
    from src.models.review_feedback import ReviewFeedbackItem, GTUpdateCandidate
    fb_q = select(func.count(ReviewFeedbackItem.id)).where(
        ReviewFeedbackItem.brand_id == brand.id,
        ReviewFeedbackItem.status == "pending",
    )
    fb_pending = (await db.execute(fb_q)).scalar() or 0
    gt_q = select(func.count(GTUpdateCandidate.id)).where(
        GTUpdateCandidate.brand_id == brand.id,
        GTUpdateCandidate.status == "pending",
    )
    gt_pending = (await db.execute(gt_q)).scalar() or 0

    # Permissions
    can_review = user.role in ("admin", "analyst", "gt_reviewer", "hallucination_reviewer",
                               "senior_reviewer") \
                 or user.platform_role in ("system_owner", "system_admin")
    can_batch = user.role in ("admin", "senior_reviewer") \
                or user.platform_role in ("system_owner", "system_admin")
    is_senior = user.role == "senior_reviewer" or user.platform_role in ("system_owner", "system_admin")

    # Enrich review items with batch selection metadata
    for item in review_items:
        sev = item["severity"]
        item["can_select"] = sev not in ("P0",) and can_batch
        if sev == "P1" and not is_senior:
            item["can_select"] = False
        item["select_disabled_reason"] = ""
        if sev == "P0":
            item["select_disabled_reason"] = "P0 高风险样本必须逐条审核"
        elif sev == "P1" and not is_senior:
            item["select_disabled_reason"] = "P1 需要高级审核员权限才能批量"

    total = pending + claimed + completed + skipped
    completion_rate = round((completed + skipped) / total, 2) if total > 0 else 0

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "review_queue": {
            "pending": pending, "claimed": claimed,
            "completed": completed, "skipped": skipped,
            "items": review_items,
        },
        "review_stats": {
            "pending": pending, "claimed": claimed,
            "completed": completed, "skipped": skipped,
            "total": total, "completion_rate": completion_rate,
            "feedback_pending": fb_pending + gt_pending,
        },
        "filters": {
            "severities": ["P0", "P1", "P2", "Info"],
            "review_statuses": ["pending", "claimed", "completed", "skipped"],
            "priorities": ["high", "medium", "low"],
        },
        "permissions": {
            "can_review": can_review,
            "can_batch": can_batch,
            "can_export": can_batch,
        },
        "clusters": [],
        "total": total,
    }
