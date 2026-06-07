"""View model for GT Search page."""

from sqlalchemy.ext.asyncio import AsyncSession
from src.models.brand import Brand
from src.models.user import User
from src.config import settings
from src.schemas.gt_field_registry import GT_FIELD_REGISTRY
from src.search import get_gt_search_adapters


async def build_gt_search_vm(brand: Brand, user: User, db: AsyncSession) -> dict:
    adapters = get_gt_search_adapters(settings)

    providers = []
    for a in adapters:
        providers.append({
            "name": a.name,
            "label": PROVIDER_LABELS.get(a.name, a.name),
            "status": a.status,
            "is_available": a.is_available(),
            "is_fallback": getattr(a, "is_fallback", False),
            "status_badge_color": STATUS_COLORS.get(a.status, "gray"),
            "status_text": STATUS_TEXT.get(a.status, a.status),
        })

    # Group fields by category for the dropdown
    field_groups = {}
    for key, fdef in sorted(GT_FIELD_REGISTRY.items()):
        cat = getattr(fdef, "category", "other")
        if cat not in field_groups:
            field_groups[cat] = []
        field_groups[cat].append({
            "key": key,
            "label": fdef.label if hasattr(fdef, "label") else key,
            "required": getattr(fdef, "required", False),
        })

    return {
        "brand": {
            "id": str(brand.id), "name": brand.name,
            "aliases": brand.aliases or [],
        },
        "providers": providers,
        "field_groups": field_groups,
        "permissions": {
            "can_search": True,
            "can_create_candidate": True,
            "can_approve": user.role in ("admin", "gt_reviewer"),
        },
    }


PROVIDER_LABELS = {
    "tavily": "Tavily Search",
    "google_cse": "Google CSE",
    "brave": "Brave Search",
    "duckduckgo": "DuckDuckGo",
}

STATUS_COLORS = {
    "enabled": "green",
    "disabled": "gray",
    "pending_config": "yellow",
    "auth_failed": "red",
    "rate_limited": "orange",
    "quota_exhausted": "orange",
    "error": "red",
}

STATUS_TEXT = {
    "enabled": "已启用",
    "disabled": "未启用",
    "pending_config": "等待配置",
    "auth_failed": "认证失败",
    "rate_limited": "已限流",
    "quota_exhausted": "额度耗尽",
    "error": "错误",
}
