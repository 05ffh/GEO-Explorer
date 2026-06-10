"""Platform variants API — generate, review, approve, reject, export variants."""

import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.content_package import ContentPackage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["platform_variants"])


class ApproveRequest(BaseModel):
    notes: str = ""


class RejectRequest(BaseModel):
    reason: str


class PublishUrlRequest(BaseModel):
    platform: str
    target: str
    variant_id: str
    published_url: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/content-packages/{cp_id}/platform-variants")
async def list_variants(cp_id: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """P0-9: List all platform variants for a ContentPackage."""
    cp = (await db.execute(
        select(ContentPackage).where(ContentPackage.id == cp_id)
    )).scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="ContentPackage not found")
    if cp.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")

    pv = cp.platform_variants or {}
    result = {}
    for platform, variants in pv.items():
        result[platform] = [
            {"format": v.get("format"), "target": v.get("target"),
             "theme": v.get("theme"), "status": v.get("status"),
             "version": v.get("version"), "title": v.get("title", v.get("seo_title", v.get("entry_name", "")))}
            for v in variants
        ]
    return {"cp_id": str(cp.id), "variants": result,
            "gt_snapshot_hash": cp.gt_snapshot_hash}


@router.post("/content-packages/{cp_id}/platform-variants/generate")
async def generate_variants(cp_id: str, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """P0-9: Generate platform variants for a ContentPackage using LLM."""
    cp = (await db.execute(
        select(ContentPackage).where(ContentPackage.id == cp_id)
    )).scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="ContentPackage not found")
    if cp.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from src.models.ground_truth import GroundTruthVersion
    from src.actions.platform_adapter import generate_platform_variants
    from src.actions.platform_schemas import build_publish_target

    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == cp.brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalar_one_or_none()
    if not gt:
        raise HTTPException(status_code=400, detail="No active GT found")

    gt_json = gt.get_flat_json() if hasattr(gt, "get_flat_json") else gt.ground_truth_json
    brand_name = str(gt_json.get("official_name", "Brand"))

    variants = {}
    for ci in (cp.content_items or []):
        theme = {
            "theme": ci.get("theme", "品牌介绍"),
            "content_type": ci.get("type", "Organization"),
            "fields": ci.get("source_fields", []),
            "publish_target": "about",
        }
        facts = {f: gt_json.get(f, "") for f in ci.get("source_fields", []) if f in gt_json}
        platform_variants = await generate_platform_variants(
            brand_name=brand_name, gt_facts=facts, theme=theme,
            fact_ids=list(facts.keys()), evidence_ids=[],
        )
        for plat, vlist in platform_variants.items():
            variants.setdefault(plat, []).extend(vlist)

    cp.platform_variants = variants
    import hashlib
    raw = "|".join(f"{k}={v}" for k, v in sorted(gt_json.items()) if v)
    cp.gt_snapshot_hash = hashlib.sha256(raw.encode() if raw else b"empty").hexdigest()[:16]
    await db.commit()

    total = sum(len(vlist) for vlist in variants.values())
    return {"cp_id": str(cp.id), "variant_count": total, "platforms": list(variants.keys())}


@router.post("/content-packages/{cp_id}/platform-variants/approve/{plat}/{idx}")
async def approve_variant(cp_id: str, plat: str, idx: int,
                           req: ApproveRequest, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """Approve a single platform variant."""
    cp = (await db.execute(
        select(ContentPackage).where(ContentPackage.id == cp_id)
    )).scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="ContentPackage not found")

    pv = cp.platform_variants or {}
    plat_variants = pv.get(plat, [])
    if idx >= len(plat_variants):
        raise HTTPException(status_code=404, detail="Variant not found")

    variant = plat_variants[idx]
    from src.actions.platform_compliance import check_compliance
    comp = check_compliance(variant, variant.get("target", ""))
    if comp["status"] == "blocked":
        raise HTTPException(status_code=400, detail="Compliance blocked — fix high-severity issues first")

    variant["status"] = "approved"
    pv[plat] = plat_variants
    cp.platform_variants = pv
    await db.commit()

    return {"cp_id": str(cp.id), "platform": plat, "index": idx, "status": "approved"}


@router.post("/content-packages/{cp_id}/platform-variants/reject/{plat}/{idx}")
async def reject_variant(cp_id: str, plat: str, idx: int,
                          req: RejectRequest, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Reject a platform variant."""
    if not req.reason.strip():
        raise HTTPException(status_code=422, detail="Reason required")

    cp = (await db.execute(
        select(ContentPackage).where(ContentPackage.id == cp_id)
    )).scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="ContentPackage not found")

    pv = cp.platform_variants or {}
    plat_variants = pv.get(plat, [])
    if idx >= len(plat_variants):
        raise HTTPException(status_code=404, detail="Variant not found")

    variant = plat_variants[idx]
    variant["status"] = "draft"
    variant["reject_reason"] = req.reason
    pv[plat] = plat_variants
    cp.platform_variants = pv
    await db.commit()

    return {"cp_id": str(cp.id), "platform": plat, "index": idx, "status": "rejected"}


@router.post("/content-packages/{cp_id}/platform-variants/publish-url")
async def set_publish_url(cp_id: str, req: PublishUrlRequest,
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """P0-4: Record published URL for a manually published variant."""
    cp = (await db.execute(
        select(ContentPackage).where(ContentPackage.id == cp_id)
    )).scalar_one_or_none()
    if not cp:
        raise HTTPException(status_code=404, detail="ContentPackage not found")

    pv = cp.platform_variants or {}
    found = False
    for plat, vlist in pv.items():
        for v in vlist:
            if v.get("variant_id") == req.variant_id:
                v["published_url"] = req.published_url
                v["published_at"] = datetime.now(timezone.utc).isoformat()
                v["status"] = "published"
                found = True

    if not found:
        raise HTTPException(status_code=404, detail="Variant not found")

    cp.platform_variants = pv
    await db.commit()
    return {"cp_id": str(cp.id), "status": "published_url_recorded"}
