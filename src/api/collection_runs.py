from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from src.database import get_db
from src.api.deps import get_current_user, get_org_brand_or_404
from src.models.user import User
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult

router = APIRouter(tags=["collections"])


@router.post("/api/brands/{brand_id}/collections", status_code=202)
async def trigger_collection(
    brand_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from src.collector.tasks import collect_brand_task

    await get_org_brand_or_404(brand_id, user, db)
    task = collect_brand_task.delay(brand_id, str(user.organization_id))
    return {
        "task_id": task.id,
        "brand_id": brand_id,
        "status": "queued",
    }


@router.get("/api/brands/{brand_id}/collections")
async def list_collections(
    brand_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_org_brand_or_404(brand_id, user, db)
    q = select(CollectionRun).where(
        CollectionRun.brand_id == brand_id,
        CollectionRun.organization_id == user.organization_id,
    ).order_by(desc(CollectionRun.created_at))
    q = q.offset((page - 1) * page_size).limit(page_size)
    results = (await db.execute(q)).scalars().all()
    return {"items": results, "page": page, "page_size": page_size}


@router.get("/api/collections/{collection_id}")
async def get_collection(
    collection_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = (await db.execute(
        select(CollectionRun).where(
            CollectionRun.id == collection_id,
            CollectionRun.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not run:
        return {"detail": "Not found"}, 404
    return {"collection": run}
