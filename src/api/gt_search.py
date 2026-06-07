"""GT Search API routes — Tavily-first evidence search + approve/reject."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user
from src.config import settings
from src.models.user import User
from src.models.brand import Brand
from src.models.gt_candidate import GroundTruthCandidate
from src.models.ground_truth import GroundTruthVersion
from src.models.audit_log import AuditLog
from src.services.audit import add_audit_log
from src.services.gt_search import GTSearchService
from src.search import get_gt_search_adapters

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["gt_search"])


# ── Request/Response models ───────────────────────────────────────────────────


class SearchRequest(BaseModel):
    field_name: str
    manual_query: str | None = None
    limit: int = 10


class GenerateCandidateRequest(BaseModel):
    field_name: str
    proposed_value: str
    extraction_method: str = "manual"
    selected_result_indexes: list[int] = []


class ApproveRequest(BaseModel):
    notes: str = ""


class RejectRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason is required for rejection")
        return v.strip()


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_brand_or_404(brand_id: uuid.UUID, user: User, db: AsyncSession) -> Brand:
    brand = (await db.execute(
        select(Brand).where(Brand.id == brand_id)
    )).scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    if brand.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied: cross-org")
    return brand


def _build_gt_search_service(db: AsyncSession) -> GTSearchService:
    adapters = get_gt_search_adapters(settings)
    return GTSearchService(adapters=adapters, db=db)


def _audit_user(user_id: str, org_id: uuid.UUID | None = None):
    """Create a minimal user-like object for audit logging."""
    class _U:
        pass
    u = _U()
    try:
        u.id = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        u.id = None
    u.organization_id = org_id
    u.name = ""
    u.role = ""
    return u


async def _approve_candidate(
    candidate_id: uuid.UUID, db: AsyncSession,
    user_id: str, org_id: uuid.UUID | None = None, notes: str = "",
) -> dict:
    """P0-7: Approve candidate with conflict handling.

    Cases:
      - No existing GT → create GT value
      - Same value → attach evidence, update confidence
      - Different value → return conflict (requires human resolution)
    """
    candidate = (await db.execute(
        select(GroundTruthCandidate).where(GroundTruthCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status != "pending_review":
        raise HTTPException(status_code=400, detail="Candidate already processed")

    field_name = candidate.candidate_json.get("field_name", "")
    proposed_value = candidate.candidate_json.get("proposed_value", "")

    # Check existing active GT
    existing_gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == candidate.brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalars().first()

    existing_value = None
    if existing_gt:
        gt_json = existing_gt.get_flat_json() if hasattr(existing_gt, "get_flat_json") else existing_gt.ground_truth_json
        existing_value = gt_json.get(field_name)

    action = "created"
    resolved = False

    if existing_value is None:
        # Case 1: No existing GT value → create
        action = "created"
        resolved = True
    elif str(existing_value).strip() == str(proposed_value).strip():
        # Case 2: Same value → attach evidence
        action = "evidence_attached"
        resolved = True
    else:
        # Case 3: Different value → conflict
        action = "conflict"
        resolved = False

    if resolved:
        # Create or update GroundTruthVersion
        if existing_gt is None:
            new_gt = GroundTruthVersion(
                brand_id=candidate.brand_id,
                version=1,
                ground_truth_json={field_name: proposed_value},
                reviewer=user_id,
                status="active",
                required_fields_complete=False,
                user_confirmed=True,
                high_risk_fields_reviewed=False,
            )
            db.add(new_gt)
        else:
            gt_json = existing_gt.get_flat_json() if hasattr(existing_gt, "get_flat_json") else existing_gt.ground_truth_json
            gt_json[field_name] = proposed_value
            existing_gt.ground_truth_json = gt_json
            existing_gt.reviewer = user_id

        candidate.status = "promoted"
        candidate.reviewed_at = datetime.now(timezone.utc)
        candidate.reviewer_id = None
    if user_id:
        try:
            candidate.reviewer_id = uuid.UUID(user_id)
        except (ValueError, AttributeError):
            pass
    await add_audit_log(
        db=db,
        user=_audit_user(user_id, org_id),
        action=f"gt_candidate_{action}" if resolved else "gt_candidate_conflict",
        target_type="gt_candidate",
        target_id=str(candidate.id),
        detail={
            "field_name": field_name,
            "proposed_value": proposed_value,
            "existing_value": str(existing_value) if existing_value else None,
            "resolved": resolved,
            "notes": notes,
        },
        reason=notes if not resolved else "",
        brand_id=str(candidate.brand_id),
    )
    await db.commit()

    return {
        "action": action,
        "resolved": resolved,
        "candidate_id": str(candidate.id),
        "field_name": field_name,
        **({"existing_value": existing_value} if existing_value is not None else {}),
        **({"conflicting_field": field_name, "existing_value": existing_value}
           if action == "conflict" else {}),
    }


async def _reject_candidate(
    candidate_id: uuid.UUID, db: AsyncSession,
    user_id: str, reason: str,
) -> dict:
    """P0-7: Reject candidate. Reason is required."""
    if not reason or not reason.strip():
        raise ValueError("reason is required for rejection")

    candidate = (await db.execute(
        select(GroundTruthCandidate).where(GroundTruthCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    candidate.status = "rejected"
    candidate.reviewed_at = datetime.now(timezone.utc)
    candidate.reviewer_id = None
    if user_id:
        try:
            candidate.reviewer_id = uuid.UUID(user_id)
        except (ValueError, AttributeError):
            pass

    await db.flush()

    await add_audit_log(
        db=db, user=_audit_user(user_id, candidate.organization_id),
        action="gt_candidate_rejected",
        target_type="gt_candidate",
        target_id=str(candidate.id),
        detail={
            "field_name": candidate.candidate_json.get("field_name"),
            "proposed_value": candidate.candidate_json.get("proposed_value"),
        },
        reason=reason,
        brand_id=str(candidate.brand_id),
    )
    await db.commit()

    return {"action": "rejected", "candidate_id": str(candidate.id)}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/brands/{brand_id}/gt-search/providers")
async def get_providers(
    brand_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return provider status for the GT Search page."""
    brand = await _get_brand_or_404(brand_id, user, db)
    svc = _build_gt_search_service(db)
    providers = svc.get_available_providers()
    return {"brand_id": str(brand_id), "providers": providers}


@router.post("/brands/{brand_id}/gt-search/search")
async def search_evidence(
    brand_id: uuid.UUID,
    req: SearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute evidence search across enabled providers."""
    brand = await _get_brand_or_404(brand_id, user, db)
    svc = _build_gt_search_service(db)
    queries = svc.generate_queries(brand, req.field_name, req.manual_query)
    results = await svc.search(
        brand, req.field_name, req.manual_query, limit=req.limit,
    )
    return {
        "brand_id": str(brand_id),
        "field_name": req.field_name,
        "queries_used": queries[:3],
        "results": [
            {
                "title": r.title, "url": r.url, "snippet": r.snippet,
                "provider": r.provider, "rank": r.rank,
                "source_tier": r.source_tier,
            }
            for r in results
        ],
        "result_count": len(results),
    }


@router.post("/brands/{brand_id}/gt-search/generate-candidate")
async def generate_candidate(
    brand_id: uuid.UUID,
    req: GenerateCandidateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a GT Candidate from search results. Status: pending_review."""
    brand = await _get_brand_or_404(brand_id, user, db)

    if not req.proposed_value or not req.proposed_value.strip():
        raise HTTPException(status_code=422, detail="proposed_value is required")

    svc = _build_gt_search_service(db)
    all_results = await svc.search(brand, req.field_name, limit=10)

    # Select specific results or use first 5
    if req.selected_result_indexes:
        selected = [all_results[i] for i in req.selected_result_indexes
                    if 0 <= i < len(all_results)]
    else:
        selected = all_results[:5]

    candidate = await svc.generate_candidate(
        brand_id=brand.id, org_id=brand.organization_id,
        field_name=req.field_name, proposed_value=req.proposed_value,
        extraction_method=req.extraction_method,
        search_results=selected, user_id=str(user.id),
    )
    return {
        "candidate_id": str(candidate.id),
        "status": candidate.status,
        "evidence_count": len(selected),
        "field_name": req.field_name,
    }


@router.post("/gt-candidates/{candidate_id}/approve")
async def approve_candidate(
    candidate_id: uuid.UUID,
    req: ApproveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a GT candidate → write to GT (with conflict handling)."""
    candidate = (await db.execute(
        select(GroundTruthCandidate).where(GroundTruthCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied: cross-org")

    result = await _approve_candidate(
        candidate_id=candidate_id, db=db,
        user_id=str(user.id), org_id=user.organization_id, notes=req.notes,
    )
    return result


@router.post("/gt-candidates/{candidate_id}/reject")
async def reject_candidate(
    candidate_id: uuid.UUID,
    req: RejectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject a GT candidate. Reason is required."""
    candidate = (await db.execute(
        select(GroundTruthCandidate).where(GroundTruthCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied: cross-org")

    try:
        result = await _reject_candidate(
            candidate_id=candidate_id, db=db,
            user_id=str(user.id), reason=req.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return result
