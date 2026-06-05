"""P2-4: Hallucination review API — queue, claim, review, batch, feedback, calibration."""
from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.database import get_db
from src.api.deps import get_current_user, get_org_brand_or_404
from src.models.user import User
from src.models.hallucination import HallucinationResult
from src.models.hallucination_review_log import HallucinationReviewLog
from src.services.review_feedback_service import review_service, VALID_REVIEW_DECISIONS

router = APIRouter(tags=["hallucinations"])


def _can_review(user: User) -> bool:
    return user.role in ("admin", "analyst", "gt_reviewer", "hallucination_reviewer",
                         "senior_reviewer", "template_reviewer") \
           or user.platform_role in ("system_owner", "system_admin")

def _can_batch(user: User) -> bool:
    return user.role in ("admin", "senior_reviewer") \
           or user.platform_role in ("system_owner", "system_admin")


class ReviewRequest(BaseModel):
    verdict: str = ""  # supported | contradicted | unsupported | not_about_brand | generic_statement | template_invalid | gt_insufficient | ambiguous | not_checkable
    notes: str = ""
    decision: str = ""  # review_decision enum
    corrected_value: str = ""
    severity: str = ""


class BatchReviewRequest(BaseModel):
    result_ids: list[str]
    decision: str = "skip"
    reason: str = Field(min_length=1)
    dry_run_token: str = ""
    idempotency_key: str = ""


class ClaimRequest(BaseModel):
    pass


@router.get("/api/hallucinations/review-queue")
async def review_queue(
    status: str = Query("pending", description="pending|claimed|completed|skipped|reopened"),
    priority: str | None = Query(None),
    severity: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_review(user):
        raise HTTPException(403, "无权访问审核队列")
    return await review_service.get_review_queue(
        db, org_id=user.organization_id, status=status,
        priority=priority, severity=severity, page=page, page_size=page_size,
    )


@router.post("/api/hallucinations/{hallucination_id}/claim")
async def claim_review_item(
    hallucination_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_review(user):
        raise HTTPException(403, "无权认领审核项")
    try:
        result = await review_service.claim(db, hallucination_id, user)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/hallucinations/{hallucination_id}/review")
async def review_hallucination(
    hallucination_id: str,
    body: ReviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_review(user):
        raise HTTPException(403, "无权审核")
    decision = body.decision or body.verdict  # backward compat
    try:
        result = await review_service.complete_review(
            db, hallucination_id, user,
            decision=decision, notes=body.notes,
            verdict=body.verdict, severity=body.severity,
            corrected_value=body.corrected_value,
        )
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/hallucinations/{hallucination_id}/skip")
async def skip_review_item(
    hallucination_id: str,
    reason: str = Query(min_length=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_review(user):
        raise HTTPException(403, "无权跳过")
    try:
        result = await review_service.skip_review(db, hallucination_id, user, reason)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/hallucinations/{hallucination_id}/reopen")
async def reopen_review_item(
    hallucination_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_review(user):
        raise HTTPException(403, "无权重新打开")
    try:
        result = await review_service.reopen(db, hallucination_id, user)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/hallucinations/{hallucination_id}/release")
async def release_claim(
    hallucination_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_review(user):
        raise HTTPException(403, "无权释放认领")
    try:
        result = await review_service.release_claim(db, hallucination_id)
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/hallucinations/batch-review/dry-run")
async def batch_review_dry_run(
    body: BatchReviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_batch(user):
        raise HTTPException(403, "无权批量审核")
    return await review_service.batch_dry_run(db, body.result_ids)


@router.post("/api/hallucinations/batch-review")
async def batch_review(
    body: BatchReviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_batch(user):
        raise HTTPException(403, "无权批量审核")
    try:
        if body.decision == "skip":
            result = await review_service.batch_skip(
                db, body.result_ids, user, body.reason,
                dry_run_token=body.dry_run_token,
                idempotency_key=body.idempotency_key)
        else:
            raise HTTPException(400, "批量操作仅支持 skip")
        await db.commit()
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/hallucinations/review-feedback")
async def review_feedback_summary(
    brand_id: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_review(user):
        raise HTTPException(403, "无权查看反馈摘要")
    from src.models.review_feedback import ReviewFeedbackItem, GTUpdateCandidate
    q = select(ReviewFeedbackItem).where(ReviewFeedbackItem.status == "pending")
    if brand_id:
        q = q.where(ReviewFeedbackItem.brand_id == brand_id)
    items = (await db.execute(q.limit(50))).scalars().all()
    gt_q = select(GTUpdateCandidate).where(GTUpdateCandidate.status == "pending")
    if brand_id:
        gt_q = gt_q.where(GTUpdateCandidate.brand_id == brand_id)
    gt_candidates = (await db.execute(gt_q.limit(50))).scalars().all()
    return {
        "feedback_items": [{"id": str(i.id), "type": i.feedback_type, "summary": i.summary,
                            "status": i.status, "priority": i.priority} for i in items],
        "gt_candidates": [{"id": str(c.id), "field_name": c.field_name,
                           "current": c.current_gt_value[:100], "proposed": c.proposed_value[:100],
                           "status": c.status} for c in gt_candidates],
    }


@router.get("/api/hallucinations/calibration-export")
async def export_calibration_samples(
    limit: int = Query(100, le=500),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_batch(user):
        raise HTTPException(403, "无权导出校准样本")
    return await review_service.export_calibration_samples(db, limit=limit)


@router.get("/api/hallucinations/{hallucination_id}/review-history")
async def review_history(
    hallucination_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    logs = (await db.execute(
        select(HallucinationReviewLog).where(
            HallucinationReviewLog.hallucination_result_id == hallucination_id,
        ).order_by(HallucinationReviewLog.created_at.desc())
    )).scalars().all()
    return [{"action": l.action, "reviewer_id": str(l.reviewer_id) if l.reviewer_id else None,
             "old_verdict": l.old_verdict, "new_verdict": l.new_verdict,
             "decision": l.review_decision, "notes": l.notes,
             "created_at": l.created_at.isoformat() if l.created_at else None} for l in logs]


# ── Legacy list endpoint ────────────────────────────────────────────────────

@router.get("/api/brands/{brand_id}/hallucinations")
async def list_hallucinations(
    brand_id: str,
    severity: str | None = Query(None),
    verdict: str | None = Query(None),
    claim_type: str | None = Query(None),
    predicate_type: str | None = Query(None),
    evidence_strength: str | None = Query(None),
    human_reviewed: bool | None = Query(None),
    review_status: str | None = Query(None),
    needs_human_review: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_org_brand_or_404(brand_id, user, db)
    q = select(HallucinationResult).where(HallucinationResult.brand_id == brand_id)
    if severity: q = q.where(HallucinationResult.severity == severity)
    if verdict: q = q.where(HallucinationResult.verdict == verdict)
    if claim_type: q = q.where(HallucinationResult.claim_type == claim_type)
    if predicate_type: q = q.where(HallucinationResult.predicate_type == predicate_type)
    if human_reviewed is not None: q = q.where(HallucinationResult.human_reviewed == human_reviewed)
    if review_status: q = q.where(HallucinationResult.review_status == review_status)
    if needs_human_review is not None: q = q.where(HallucinationResult.needs_human_review == needs_human_review)
    q = q.order_by(desc(HallucinationResult.created_at))
    q = q.offset((page - 1) * page_size).limit(page_size)
    results = (await db.execute(q)).scalars().all()
    return {"items": results, "page": page, "page_size": page_size}
