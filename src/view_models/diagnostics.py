"""Diagnostic launcher ViewModel — search/create/identify/launch flow."""
from sqlalchemy import select, desc
from src.models.brand import Brand
from src.models.collection_run import CollectionRun


async def build_diagnostics_vm(user, db, search_query: str = "") -> dict:
    """Build view model for /diagnostics/new page.

    When search_query is provided, searches existing brands.
    Always shows recent brands and recent runs.
    """
    # Search results
    search_results = []
    if search_query and len(search_query.strip()) >= 1:
        q = search_query.strip()
        rows = (await db.execute(
            select(Brand).where(
                Brand.organization_id == user.organization_id,
                Brand.name.ilike(f"%{q}%"),
            ).limit(10)
        )).scalars().all()
        search_results = [{"id": str(b.id), "name": b.name, "industry": b.industry or ""}
                          for b in rows]

    # Recent brands (last 10)
    recent_brands = []
    all_brands = (await db.execute(
        select(Brand).where(
            Brand.organization_id == user.organization_id,
        ).order_by(desc(Brand.updated_at)).limit(10)
    )).scalars().all()
    recent_brands = [{"id": str(b.id), "name": b.name, "industry": b.industry or ""}
                     for b in all_brands]

    # Recent runs (last 5)
    recent_runs_raw = (await db.execute(
        select(CollectionRun).where(
            CollectionRun.organization_id == user.organization_id,
        ).order_by(desc(CollectionRun.created_at)).limit(5)
    )).scalars().all()

    # Build brand lookup for run display
    brand_map = {str(b.id): b.name for b in all_brands}

    recent_runs = []
    for r in recent_runs_raw:
        recent_runs.append({
            "id": str(r.id),
            "brand_id": str(r.brand_id),
            "brand_name": brand_map.get(str(r.brand_id), "未知品牌"),
            "status": r.collection_status,
            "success_count": r.success_count or 0,
            "total_queries": r.total_queries or 0,
            "created_at": str(r.created_at)[:19] if r.created_at else "",
        })

    return {
        "search_query": search_query,
        "search_results": search_results,
        "has_results": len(search_results) > 0,
        "recent_brands": recent_brands,
        "has_brands": len(recent_brands) > 0,
        "recent_runs": recent_runs,
        "has_runs": len(recent_runs) > 0,
    }
