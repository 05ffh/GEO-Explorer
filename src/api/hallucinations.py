from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.database import get_db
from src.api.deps import get_current_user, get_org_brand_or_404
from src.models.user import User
from src.models.hallucination import HallucinationResult

router = APIRouter(tags=["hallucinations"])


class ReviewRequest(BaseModel):
    verdict: str  # correct | incorrect | uncertain | ignored
    notes: str = ""


@router.get("/api/brands/{brand_id}/hallucinations")
async def list_hallucinations(
    brand_id: str,
    severity: str | None = Query(None),
    verdict: str | None = Query(None),
    claim_type: str | None = Query(None, description="fact|opinion|speculation|unknown"),
    predicate_type: str | None = Query(None, description="identity|industry|product|positioning|..."),
    human_reviewed: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_org_brand_or_404(brand_id, user, db)
    q = select(HallucinationResult).where(
        HallucinationResult.brand_id == brand_id,
    )
    if severity:
        q = q.where(HallucinationResult.severity == severity)
    if verdict:
        q = q.where(HallucinationResult.verdict == verdict)
    if claim_type:
        q = q.where(HallucinationResult.claim_type == claim_type)
    if predicate_type:
        q = q.where(HallucinationResult.predicate_type == predicate_type)
    if human_reviewed is not None:
        q = q.where(HallucinationResult.human_reviewed == human_reviewed)
    q = q.order_by(desc(HallucinationResult.created_at))
    q = q.offset((page - 1) * page_size).limit(page_size)
    results = (await db.execute(q)).scalars().all()
    return {"items": results, "page": page, "page_size": page_size}


@router.post("/api/hallucinations/{hallucination_id}/review")
async def review_hallucination(
    hallucination_id: str,
    body: ReviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    h = (await db.execute(
        select(HallucinationResult).where(HallucinationResult.id == hallucination_id)
    )).scalar_one_or_none()
    if not h:
        return {"detail": "Not found"}, 404

    h.human_reviewed = True
    h.human_verdict = body.verdict
    h.reviewer_id = user.id
    from datetime import datetime
    h.reviewed_at = datetime.utcnow()
    await db.commit()
    return {"id": str(h.id), "verdict": h.human_verdict}
