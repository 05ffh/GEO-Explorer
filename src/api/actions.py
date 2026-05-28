from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.database import get_db
from src.api.deps import get_current_user, get_org_brand_or_404
from src.models.user import User
from src.models.action_plan import ActionPlan
from src.actions.engine import update_action_status, generate_action_plans

router = APIRouter(tags=["actions"])


class ActionUpdate(BaseModel):
    status: str | None = None
    owner_id: str | None = None
    notes: str | None = None


@router.get("/api/brands/{brand_id}/actions")
async def list_actions(
    brand_id: str,
    status: str | None = Query(None),
    priority: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_org_brand_or_404(brand_id, user, db)
    q = select(ActionPlan).where(
        ActionPlan.brand_id == brand_id,
        ActionPlan.organization_id == user.organization_id,
    )
    if status:
        q = q.where(ActionPlan.status == status)
    if priority:
        q = q.where(ActionPlan.priority == priority)
    q = q.order_by(desc(ActionPlan.created_at))
    q = q.offset((page - 1) * page_size).limit(page_size)
    results = (await db.execute(q)).scalars().all()
    return {"items": results, "page": page, "page_size": page_size}


@router.put("/api/actions/{action_id}")
async def update_action(
    action_id: str,
    body: ActionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.status:
        action = await update_action_status(action_id, body.status, db)
    else:
        action = (await db.execute(
            select(ActionPlan).where(ActionPlan.id == action_id)
        )).scalar_one_or_none()
        if not action:
            return {"detail": "Not found"}, 404

    if body.owner_id is not None:
        action.owner_id = body.owner_id
    if body.notes is not None:
        action.notes = body.notes
    await db.commit()
    return {"id": str(action.id), "status": action.status}


@router.post("/api/brands/{brand_id}/actions/generate")
async def generate_actions(
    brand_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_org_brand_or_404(brand_id, user, db)
    plans = await generate_action_plans(brand_id, user.organization_id, db)
    return {"generated": len(plans)}
