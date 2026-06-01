"""Publishing pause mechanism — emergency stop for publishing operations (P2-4)."""
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.publishing.events import write_publish_event

logger = logging.getLogger(__name__)

# In-memory pause state (backed by Redis in production)
_global_pause = False
_org_pauses: dict[str, bool] = {}


def is_publishing_paused(org_id: str | None = None) -> tuple[bool, str]:
    """Check if publishing is paused. Returns (paused, reason)."""
    if _global_pause:
        return True, "global_pause"
    if org_id and _org_pauses.get(org_id, False):
        return True, "organization_pause"
    return False, ""


async def set_global_pause(db: AsyncSession, paused: bool, actor_id=None) -> dict:
    """Set global publishing pause."""
    global _global_pause
    _global_pause = paused
    event_type = "publish_paused" if paused else "publish_resumed"
    # Write event for audit (org_id=None for global events)
    await write_publish_event(db, organization_id=actor_id or None,
                               event_type=event_type,
                               message=f"Global publish {'paused' if paused else 'resumed'}",
                               created_by=actor_id)
    return {"global_pause": paused}


async def set_org_pause(db: AsyncSession, org_id: str, paused: bool, actor_id=None) -> dict:
    """Set organization-level publishing pause."""
    _org_pauses[org_id] = paused
    event_type = "publish_paused" if paused else "publish_resumed"
    await write_publish_event(db, organization_id=org_id,
                               event_type=event_type,
                               message=f"Org publish {'paused' if paused else 'resumed'}",
                               created_by=actor_id)
    return {"org_pause": paused, "org_id": org_id}


async def check_target_pause(db: AsyncSession, target_id) -> tuple[bool, str]:
    """Check if a specific target is paused."""
    row = (await db.execute(text(
        "SELECT status, health_status FROM publish_targets WHERE id = :id"
    ), {"id": target_id})).fetchone()
    if not row:
        return False, ""
    if row.status == "paused":
        return True, "target_paused"
    if row.health_status == "paused":
        return True, "target_health_paused"
    return False, ""
