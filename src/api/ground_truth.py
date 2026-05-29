from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import get_db
from src.api.deps import get_current_user, get_org_brand_or_404
from src.config import settings
from src.models.user import User
from src.models.gt_candidate import GroundTruthCandidate
from src.models.gt_review import GroundTruthReview
from src.models.ground_truth import GroundTruthVersion

router = APIRouter(prefix="/api", tags=["ground_truth"])


class FieldReview(BaseModel):
    field_name: str
    action: str  # accept | edit | delete | uncertain
    new_value: str | None = None


class ReviewRequest(BaseModel):
    field_reviews: list[FieldReview]
    notes: str = ""


@router.get("/brands/{brand_id}/gt-candidates")
async def list_gt_candidates(
    brand_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_org_brand_or_404(brand_id, user, db)
    candidates = (await db.execute(
        select(GroundTruthCandidate)
        .where(GroundTruthCandidate.brand_id == brand.id)
        .order_by(GroundTruthCandidate.created_at.desc())
    )).scalars().all()
    return {
        "brand_id": str(brand.id),
        "candidates": candidates,
        "high_risk_fields": settings.gt_high_risk_fields,
    }


@router.post("/gt-candidates/{candidate_id}/review")
async def review_gt_candidate(
    candidate_id: str,
    body: ReviewRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    candidate = (await db.execute(
        select(GroundTruthCandidate).where(GroundTruthCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    field_changes = {}
    for fr in body.field_reviews:
        field_changes[fr.field_name] = {
            "action": fr.action,
            "new_value": fr.new_value,
        }

    review = GroundTruthReview(
        candidate_id=candidate.id,
        reviewer_id=user.id,
        action="reviewed",
        field_changes_json=field_changes,
        review_notes=body.notes,
    )
    db.add(review)

    _apply_field_reviews(candidate, body.field_reviews)

    await db.commit()
    return {"status": "reviewed", "candidate_id": str(candidate.id)}


@router.post("/gt-candidates/{candidate_id}/promote")
async def promote_candidate_to_active(
    candidate_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    candidate = (await db.execute(
        select(GroundTruthCandidate).where(GroundTruthCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    completeness = _check_required_fields(candidate)
    if not completeness["complete"]:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required fields: {completeness['missing']}",
        )

    if not _check_high_risk_completion(candidate):
        raise HTTPException(status_code=400, detail="High-risk fields must be reviewed before promotion")

    # Deactivate existing active GT version
    existing = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == candidate.brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalars().all()
    for gt in existing:
        gt.status = "superseded"

    # Create new active GT version from candidate
    latest_version = await _get_latest_version(candidate.brand_id, db)
    new_gt = GroundTruthVersion(
        brand_id=candidate.brand_id,
        version=latest_version + 1,
        ground_truth_json=candidate.candidate_json,
        status="active",
        reviewer=user.name or "",
        user_confirmed=True,
        high_risk_fields_reviewed=True,
        required_fields_complete=True,
        gt_coverage_rate=_compute_coverage(candidate),
    )
    db.add(new_gt)
    candidate.status = "promoted"
    await db.commit()
    return {"status": "promoted", "gt_version_id": str(new_gt.id)}


def _apply_field_reviews(candidate: GroundTruthCandidate, field_reviews: list[FieldReview]) -> None:
    for fr in field_reviews:
        if fr.action == "accept":
            pass  # keep existing value
        elif fr.action == "edit" and fr.new_value is not None:
            candidate.candidate_json[fr.field_name] = fr.new_value
        elif fr.action == "delete":
            candidate.candidate_json.pop(fr.field_name, None)
        elif fr.action == "uncertain":
            candidate.candidate_json[fr.field_name] = f"[UNCERTAIN] {candidate.candidate_json.get(fr.field_name, '')}"


def _check_high_risk_completion(candidate: GroundTruthCandidate) -> bool:
    reviewed_fields = set(candidate.candidate_json.keys())
    high_risk = set(settings.gt_high_risk_fields)
    relevant_high_risk = high_risk & reviewed_fields
    if not relevant_high_risk:
        return True  # no high-risk fields collected, nothing to review
    # Check no high-risk field has UNCERTAIN marker
    for field in relevant_high_risk:
        val = candidate.candidate_json.get(field, "")
        if isinstance(val, str) and val.startswith("[UNCERTAIN]"):
            return False
    return True


def _check_required_fields(candidate: GroundTruthCandidate) -> dict:
    have = set(candidate.candidate_json.keys())
    need = set(settings.gt_required_fields)
    missing = need - have
    return {"complete": len(missing) == 0, "missing": list(missing)}


async def _get_latest_version(brand_id, db: AsyncSession) -> int:
    gt = (await db.execute(
        select(GroundTruthVersion)
        .where(GroundTruthVersion.brand_id == brand_id)
        .order_by(GroundTruthVersion.version.desc())
    )).scalars().first()
    return gt.version if gt else 0


def _compute_coverage(candidate: GroundTruthCandidate) -> float:
    required = set(settings.gt_required_fields)
    have = set(candidate.candidate_json.keys())
    if not required:
        return 1.0
    return len(have & required) / len(required)
