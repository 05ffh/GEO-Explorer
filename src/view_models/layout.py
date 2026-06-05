"""Global Layout ViewModel — generates navigation items with permission gating."""
from sqlalchemy import select


async def build_layout_vm(user, db, current_brand_id: str = "") -> dict:
    """Build the global layout context including navigation items and permissions.

    Returns a dict with:
      - diagnostic_nav: always-available diagnostic entry items
      - brand_nav: brand-scoped items (requires selected brand)
      - system_nav: org-level items
      - platform_nav: system_admin+ items
      - brand_context: selected brand info + recent brands
      - permissions: can_create_brand, can_start_diagnostic, can_access_platform
    """
    from src.models.brand import Brand

    # Brand context
    org_brands = (await db.execute(
        select(Brand).where(Brand.organization_id == user.organization_id)
        .order_by(Brand.updated_at.desc()).limit(20)
    )).scalars().all()

    brands = [{"id": str(b.id), "name": b.name, "industry": b.industry or ""}
              for b in org_brands]

    selected_brand = None
    if current_brand_id:
        for b in brands:
            if b["id"] == current_brand_id:
                selected_brand = b
                break

    # Platform access
    is_platform = user.platform_role in ("system_owner", "system_admin")
    is_system_owner = user.platform_role == "system_owner"

    return {
        "brands": brands,
        "brand_count": len(brands),
        "selected_brand": selected_brand,
        "current_brand_id": current_brand_id,
        "can_create_brand": True,
        "can_start_diagnostic": True,
        "can_access_platform": is_platform,
        "is_system_owner": is_system_owner,
    }
