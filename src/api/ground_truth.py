from typing import Literal

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
    action: Literal["accept", "edit", "delete", "uncertain"]
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
        select(GroundTruthCandidate).where(
            GroundTruthCandidate.id == candidate_id,
            GroundTruthCandidate.organization_id == user.organization_id,
        )
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
        select(GroundTruthCandidate).where(
            GroundTruthCandidate.id == candidate_id,
            GroundTruthCandidate.organization_id == user.organization_id,
        )
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

    # Evidence sufficiency check for high-risk fields
    evidence_issues = await _check_evidence_sufficiency(candidate, db)
    if evidence_issues:
        raise HTTPException(
            status_code=400,
            detail=f"Evidence insufficient for high-risk fields: {evidence_issues}",
        )

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


async def _check_evidence_sufficiency(candidate, db) -> list[str]:
    """Check that high-risk fields have sufficient evidence tier and count."""
    from src.models.gt_evidence import GroundTruthEvidence
    from src.schemas.ground_truth import HIGH_RISK_FIELD_TIER_REQUIREMENTS, SOURCE_TIERS, FIELD_EVIDENCE_REQUIREMENTS
    from sqlalchemy import select as sa_select

    evidence_rows = (await db.execute(
        sa_select(GroundTruthEvidence).where(GroundTruthEvidence.candidate_id == candidate.id)
    )).scalars().all()

    issues = []
    for field in settings.gt_high_risk_fields:
        if field not in candidate.candidate_json:
            continue

        req = HIGH_RISK_FIELD_TIER_REQUIREMENTS.get(field) or \
              FIELD_EVIDENCE_REQUIREMENTS.get(field, {}).get("min_tier", "B")
        min_sources = FIELD_EVIDENCE_REQUIREMENTS.get(field, {}).get("min_sources", 1)

        field_ev = [e for e in evidence_rows if e.field_name == field]
        req_score = SOURCE_TIERS.get(req, {}).get("score", 0.4)
        sufficient = [e for e in field_ev
                      if SOURCE_TIERS.get(e.source_tier, {}).get("score", 0) >= req_score]

        if len(field_ev) < min_sources:
            issues.append(f"{field}: need {min_sources}+ sources (has {len(field_ev)})")
        elif not sufficient and req_score > 0.3:
            issues.append(f"{field}: needs {req}-tier evidence (best: {max((e.source_tier for e in field_ev), default='none')})")

    return issues


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


# ── P1-1: Single-field GT editing (v2-aware) ─────────────────────────────

class FieldEditRequest(BaseModel):
    field_type: Literal["string", "list", "number", "object"] | None = None
    values: list[dict] = []
    reason: str = ""


@router.put("/gt/{gt_id}/fields/{field_name}")
async def edit_gt_field(
    gt_id: str,
    field_name: str,
    body: FieldEditRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    gt = (await db.execute(
        select(GroundTruthVersion).where(GroundTruthVersion.id == gt_id)
    )).scalar_one_or_none()
    if not gt:
        raise HTTPException(status_code=404, detail="GT version not found")

    from src.schemas.gt_field_registry import validate_field_name
    valid, reason = validate_field_name(field_name)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid field: {reason}")

    from src.schemas.gt_v2 import detect_gt_schema_version, GroundTruthV2, GtField

    gt_json = dict(gt.ground_truth_json or {})
    v = detect_gt_schema_version(gt_json, gt.gt_schema_version)

    if v == "v1":
        # Upgrade to v2 on first field edit
        from scripts.migrate_gt_to_v2 import migrate_one
        v2_json, _ = migrate_one(gt_json, list(gt.source_urls or []))
        gt_json = v2_json
        gt.gt_schema_version = "gt_v2"

    ft = body.field_type or "string"
    gt_json.setdefault("fields", {})[field_name] = {
        "field_type": ft,
        "values": body.values,
        "status": "reviewed",
    }

    from src.schemas.gt_v2 import compute_coverage_score, GroundTruthV2 as _V2
    try:
        _V2.model_validate(gt_json)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    gt_json["meta"] = gt_json.get("meta", {})
    gt_json["meta"]["coverage_score"] = compute_coverage_score(gt_json.get("fields", {}))
    gt_json["meta"]["last_reviewed_by"] = str(user.id)
    gt_json["meta"]["last_reviewed_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat()

    gt.ground_truth_json = gt_json
    await db.commit()
    return {"status": "updated", "gt_id": gt_id, "field": field_name}


@router.get("/gt/{gt_id}/fields/{field_name}/sources")
async def get_gt_field_sources(
    gt_id: str,
    field_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    gt = (await db.execute(
        select(GroundTruthVersion).where(GroundTruthVersion.id == gt_id)
    )).scalar_one_or_none()
    if not gt:
        raise HTTPException(status_code=404, detail="GT version not found")

    sources = gt.get_field_sources(field_name)
    return {"gt_id": gt_id, "field": field_name, "sources": sources}
