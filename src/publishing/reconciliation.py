"""Publishing reconciliation — repair stuck/stale tasks (P2-4)."""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.publishing.events import write_publish_event
from src.publishing.state_machine import transition_publish_request, update_batch_status
from src.publishing.health import assess_target_health

logger = logging.getLogger(__name__)

SENDING_TIMEOUT_MINUTES = 30
QUEUED_TIMEOUT_MINUTES = 15


async def reconcile_publish_requests(db: AsyncSession) -> dict:
    """Find and repair stuck PublishRequests."""
    now = datetime.now(timezone.utc)
    repaired = 0

    # Sending > 30 min → unknown
    stale_sending = (await db.execute(text("""
        SELECT id, organization_id, brand_id, content_package_id, publish_batch_id
        FROM publish_requests
        WHERE status = 'sending' AND updated_at < :cutoff FOR UPDATE SKIP LOCKED
    """), {"cutoff": now - timedelta(minutes=SENDING_TIMEOUT_MINUTES)})).fetchall()

    for r in stale_sending:
        await transition_publish_request(db, r.id, "unknown",
                                          message="Reconciliation: sending timeout")
        await write_publish_event(db, organization_id=r.organization_id,
                                   brand_id=r.brand_id,
                                   content_package_id=r.content_package_id,
                                   publish_batch_id=r.publish_batch_id,
                                   publish_request_id=r.id,
                                   event_type="publish_status_updated",
                                   old_status="sending", new_status="unknown",
                                   message="Reconciliation: marked unknown (sending timeout)")
        repaired += 1

    # Queued > 15 min → enqueue_failed
    stale_queued = (await db.execute(text("""
        SELECT id, organization_id, brand_id, content_package_id, publish_batch_id
        FROM publish_requests
        WHERE status = 'queued' AND updated_at < :cutoff FOR UPDATE SKIP LOCKED
    """), {"cutoff": now - timedelta(minutes=QUEUED_TIMEOUT_MINUTES)})).fetchall()

    for r in stale_queued:
        await transition_publish_request(db, r.id, "enqueue_failed",
                                          message="Reconciliation: queued timeout")
        repaired += 1

    return {"repaired": repaired, "stale_sending": len(stale_sending),
            "stale_queued": len(stale_queued)}


async def reconcile_publish_batches(db: AsyncSession) -> dict:
    """Repair PublishBatches whose requests are all terminal but batch is still running."""
    stale_batches = (await db.execute(text("""
        SELECT id FROM publish_batches WHERE status = 'running'
        AND updated_at < :cutoff FOR UPDATE SKIP LOCKED
    """), {"cutoff": datetime.now(timezone.utc) - timedelta(minutes=30)})).fetchall()

    repaired = 0
    for b in stale_batches:
        await update_batch_status(db, b.id)
        repaired += 1

    return {"repaired": repaired}


async def reconcile_publish_targets(db: AsyncSession) -> dict:
    """Repair target health that's inconsistent with consecutive_failures."""
    targets = (await db.execute(text("""
        SELECT id, organization_id FROM publish_targets
        WHERE health_status IN ('degraded', 'failing')
        AND consecutive_failures = 0 FOR UPDATE SKIP LOCKED
    """)).fetchall())

    repaired = 0
    for t in targets:
        await assess_target_health(db, t.id, t.organization_id)
        repaired += 1

    return {"repaired": repaired}


async def run_full_reconciliation(db: AsyncSession) -> dict:
    """Run all reconciliation checks."""
    requests = await reconcile_publish_requests(db)
    batches = await reconcile_publish_batches(db)
    targets = await reconcile_publish_targets(db)
    return {"requests": requests, "batches": batches, "targets": targets}
