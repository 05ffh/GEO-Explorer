"""Publishing target health — assessment, recovery, and circuit breaker (P2-4)."""
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.publishing.events import write_publish_event

logger = logging.getLogger(__name__)

HEALTH_DEGRADED_THRESHOLD = 3
HEALTH_FAILING_THRESHOLD = 5
CIRCUIT_BREAKER_OPEN_SECONDS = 1800  # 30 min


async def assess_target_health(db: AsyncSession, target_id, organization_id) -> dict:
    """Assess and update target health based on consecutive failures."""
    row = (await db.execute(text(
        "SELECT id, health_status, consecutive_failures, credential_status, status "
        "FROM publish_targets WHERE id = :id FOR UPDATE"
    ), {"id": target_id})).fetchone()
    if not row:
        return {"health_status": "unknown"}

    old_health = row.health_status
    new_health = old_health

    if row.status == "paused":
        new_health = "paused"
    elif row.status == "archived":
        new_health = "invalid"
    elif row.credential_status == "invalid":
        new_health = "invalid"
    elif row.consecutive_failures >= HEALTH_FAILING_THRESHOLD:
        new_health = "failing"
    elif row.consecutive_failures >= HEALTH_DEGRADED_THRESHOLD:
        new_health = "degraded"
    elif row.consecutive_failures == 0 and row.health_status in ("degraded", "failing"):
        new_health = "healthy"

    if new_health != old_health:
        now = datetime.now(timezone.utc)
        await db.execute(text("""
            UPDATE publish_targets SET health_status = :h, last_health_change_at = :now,
            health_reason = :reason, updated_at = :now WHERE id = :id
        """), {"h": new_health, "now": now, "reason": f"Health: {old_health} → {new_health}",
               "id": target_id})
        await write_publish_event(db, organization_id=organization_id,
                                   event_type="publish_target_health_changed",
                                   old_status=old_health, new_status=new_health,
                                   message=f"Target health: {old_health} → {new_health}")

    return {"health_status": new_health, "previous": old_health}


async def record_success(db: AsyncSession, target_id, organization_id):
    """Record a successful delivery — reset consecutive failures."""
    await db.execute(text("""
        UPDATE publish_targets SET consecutive_failures = 0,
        last_success_at = :now, updated_at = :now WHERE id = :id
    """), {"now": datetime.now(timezone.utc), "id": target_id})
    await assess_target_health(db, target_id, organization_id)


async def record_failure(db: AsyncSession, target_id, organization_id):
    """Record a failed delivery — increment consecutive failures."""
    await db.execute(text("""
        UPDATE publish_targets SET consecutive_failures = consecutive_failures + 1,
        last_failed_at = :now, failure_count = failure_count + 1,
        updated_at = :now WHERE id = :id
    """), {"now": datetime.now(timezone.utc), "id": target_id})
    await assess_target_health(db, target_id, organization_id)


async def check_circuit_breaker(db: AsyncSession, target_id) -> dict:
    """Check if a target's circuit breaker allows sending."""
    row = (await db.execute(text(
        "SELECT circuit_breaker_state, consecutive_failures, last_health_change_at "
        "FROM publish_targets WHERE id = :id"
    ), {"id": target_id})).fetchone()
    if not row:
        return {"allowed": True}

    state = row.circuit_breaker_state

    if state == "closed":
        return {"allowed": True}

    if state == "open":
        # Check if we should transition to half_open
        if row.last_health_change_at:
            elapsed = (datetime.now(timezone.utc) - row.last_health_change_at).total_seconds()
            if elapsed >= CIRCUIT_BREAKER_OPEN_SECONDS:
                await db.execute(text(
                    "UPDATE publish_targets SET circuit_breaker_state = 'half_open', "
                    "updated_at = :now WHERE id = :id"
                ), {"now": datetime.now(timezone.utc), "id": target_id})
                return {"allowed": True, "state": "half_open"}
        return {"allowed": False, "state": "open", "reason": "Circuit breaker open"}

    if state == "half_open":
        return {"allowed": True, "state": "half_open"}

    return {"allowed": True}
