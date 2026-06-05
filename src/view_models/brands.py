"""View model for brand management pages."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.models.user import User
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion
from src.models.collection_run import CollectionRun


async def build_brand_list_vm(
    user: User,
    db: AsyncSession,
    search_query: str = "",
    industry_filter: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Build view model for brand list page with GT coverage and last collection info."""
    org_id = user.organization_id

    # Base query: all brands in org
    base_q = select(Brand).where(Brand.organization_id == org_id)

    # Search filter
    if search_query:
        base_q = base_q.where(Brand.name.ilike(f"%{search_query}%"))

    # Industry filter
    if industry_filter:
        base_q = base_q.where(Brand.industry == industry_filter)

    # Count total
    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    rows = (await db.execute(
        base_q.order_by(Brand.created_at.desc()).offset(offset).limit(page_size)
    )).scalars().all()

    # Collect industry options
    industries_q = select(Brand.industry).where(
        Brand.organization_id == org_id,
        Brand.industry != "",
    ).distinct()
    industry_options = sorted(
        [r for r in (await db.execute(industries_q)).scalars().all() if r]
    )

    # Enrich each brand with GT coverage and last collection info
    brand_cards = []
    for brand in rows:
        # GT coverage: count active GT fields
        gt = (await db.execute(
            select(GroundTruthVersion).where(
                GroundTruthVersion.brand_id == brand.id,
                GroundTruthVersion.status == "active",
            )
        )).scalar_one_or_none()
        gt_field_count = len(gt.ground_truth_json) if gt else 0
        gt_total = 10  # standard GT required fields count

        # Latest collection run
        latest_run = (await db.execute(
            select(CollectionRun).where(
                CollectionRun.brand_id == brand.id,
            ).order_by(CollectionRun.started_at.desc()).limit(1)
        )).scalar_one_or_none()

        latest_collection_at = None
        if latest_run:
            latest_collection_at = latest_run.started_at.isoformat() if latest_run.started_at else None

        # Latest diagnostic run (manual trigger)
        latest_diag = (await db.execute(
            select(CollectionRun).where(
                CollectionRun.brand_id == brand.id,
                CollectionRun.trigger_type == "manual",
            ).order_by(CollectionRun.started_at.desc()).limit(1)
        )).scalar_one_or_none()

        latest_diagnostic_at = None
        if latest_diag:
            latest_diagnostic_at = latest_diag.started_at.isoformat() if latest_diag.started_at else None

        brand_cards.append({
            "id": str(brand.id),
            "name": brand.name,
            "industry": brand.industry or "未设置",
            "aliases": brand.aliases or [],
            "aliases_display": ", ".join(brand.aliases[:3]) if brand.aliases else "",
            "gt_field_count": gt_field_count,
            "gt_total": gt_total,
            "gt_coverage_pct": round(gt_field_count / gt_total * 100) if gt_total > 0 else 0,
            "latest_collection_at": latest_collection_at,
            "latest_diagnostic_at": latest_diagnostic_at,
        })

    total_pages = max(1, (total + page_size - 1) // page_size)

    return {
        "brands": brand_cards,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "search_query": search_query,
        "industry_filter": industry_filter,
        "industry_options": industry_options,
        "has_brands": total > 0,
        "has_search": bool(search_query or industry_filter),
    }
