from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import get_db
from src.api.deps import get_current_user, get_org_brand_or_404
from src.models.user import User
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion

router = APIRouter(prefix="/api/brands", tags=["brands"])


class BrandCreate(BaseModel):
    name: str
    aliases: list[str] = []
    industry: str = ""
    ground_truth: dict = {}


class BrandUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    industry: str | None = None


@router.get("")
async def list_brands(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Brand).where(Brand.organization_id == user.organization_id)
    q = q.offset((page - 1) * page_size).limit(page_size)
    results = (await db.execute(q)).scalars().all()
    return {"items": results, "page": page, "page_size": page_size}


@router.post("")
async def create_brand(
    body: BrandCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brand = Brand(
        organization_id=user.organization_id,
        name=body.name, aliases=body.aliases, industry=body.industry,
        created_by=user.id,
    )
    db.add(brand)
    await db.flush()

    if body.ground_truth:
        gt = GroundTruthVersion(
            brand_id=brand.id, version=1,
            ground_truth_json=body.ground_truth, status="active",
            reviewer=user.name,
        )
        db.add(gt)

    await db.commit()
    return {"id": str(brand.id), "name": brand.name}


@router.get("/{brand_id}")
async def get_brand(
    brand_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_org_brand_or_404(brand_id, user, db)
    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand.id,
            GroundTruthVersion.status == "active",
        )
    )).scalars().first()
    return {"brand": brand, "active_gt": gt}


@router.put("/{brand_id}")
async def update_brand(
    brand_id: str,
    body: BrandUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_org_brand_or_404(brand_id, user, db)
    if body.name is not None:
        brand.name = body.name
    if body.aliases is not None:
        brand.aliases = body.aliases
    if body.industry is not None:
        brand.industry = body.industry
    brand.updated_by = user.id
    await db.commit()
    return {"id": str(brand.id), "name": brand.name}
