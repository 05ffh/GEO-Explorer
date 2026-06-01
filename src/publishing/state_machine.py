"""Publish state machine — state transitions with FOR UPDATE locks (P2-4)."""
import logging
from datetime import datetime, timezone
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.publishing.models import PUBLISH_REQUEST_TRANSITIONS, PublishRequest, PublishBatch
from src.publishing.events import write_publish_event

logger = logging.getLogger(__name__)

VALID_PUBLISH_ACTIONS = {"create", "update", "republish", "revoke", "archive"}


async def transition_publish_request(db: AsyncSession, request_id, new_status: str,
                                      message: str = "", metadata: dict | None = None,
                                      actor_id=None) -> bool:
    """Transition a PublishRequest to a new status with FOR UPDATE lock.
    Returns True if the transition was successful, False if invalid.
    """
    rid = _to_uuid(request_id)

    # Lock the row
    result = await db.execute(
        text("SELECT id, status, organization_id, brand_id, content_package_id, "
             "publish_batch_id, publish_target_id "
             "FROM publish_requests WHERE id = :id FOR UPDATE"),
        {"id": rid},
    )
    row = result.fetchone()
    if not row:
        logger.error(f"PublishRequest not found: {request_id}")
        return False

    old_status = row.status
    allowed = PUBLISH_REQUEST_TRANSITIONS.get(old_status, [])
    if new_status not in allowed:
        logger.warning(f"Invalid transition: {old_status} -> {new_status} (request {request_id})")
        await write_publish_event(db, organization_id=row.organization_id,
                                   brand_id=row.brand_id,
                                   content_package_id=row.content_package_id,
                                   publish_batch_id=row.publish_batch_id,
                                   publish_request_id=rid,
                                   event_type="publish_status_updated",
                                   old_status=old_status, new_status=None,
                                   message=f"Invalid transition rejected: {old_status} -> {new_status}",
                                   metadata_json=metadata, created_by=actor_id)
        return False

    # Execute transition
    now = datetime.now(timezone.utc)
    extra = {}
    if new_status in ("completed", "published", "failed", "cancelled", "delivered_no_callback",
                       "rejected", "revoked", "archived"):
        extra["completed_at"] = now
    await db.execute(
        text("UPDATE publish_requests SET status = :status, updated_at = :now "
             + (", completed_at = :completed_at" if "completed_at" in extra else "")
             + " WHERE id = :id"),
        {"status": new_status, "now": now, "id": rid,
         "completed_at": extra.get("completed_at")},
    )

    await write_publish_event(db, organization_id=row.organization_id,
                               brand_id=row.brand_id,
                               content_package_id=row.content_package_id,
                               publish_batch_id=row.publish_batch_id,
                               publish_request_id=rid,
                               event_type="publish_status_updated",
                               old_status=old_status, new_status=new_status,
                               message=message, metadata_json=metadata,
                               created_by=actor_id)
    await db.flush()
    return True


async def update_batch_status(db: AsyncSession, batch_id, actor_id=None) -> dict:
    """Recompute PublishBatch status from child PublishRequests (with FOR UPDATE lock)."""
    bid = _to_uuid(batch_id)

    # Lock batch row
    batch_row = (await db.execute(
        text("SELECT * FROM publish_batches WHERE id = :id FOR UPDATE"), {"id": bid}
    )).fetchone()
    if not batch_row:
        return {"status": "unknown"}

    # Aggregate child statuses
    child_stats = (await db.execute(text("""
        SELECT status, COUNT(*) c FROM publish_requests
        WHERE publish_batch_id = :bid GROUP BY status
    """), {"bid": bid})).fetchall()

    success = failed = cancelled = total = 0
    all_terminal = True
    for r in child_stats:
        total += r.c
        if r.status in ("published", "delivered", "acknowledged", "draft_created"):
            success += r.c
        elif r.status in ("failed", "enqueue_failed", "rejected"):
            failed += r.c
        elif r.status in ("cancelled",):
            cancelled += r.c
        elif r.status not in ("revoked", "archived", "delivered_no_callback", "stale", "unknown"):
            all_terminal = False

    if total == 0:
        new_status = "cancelled"
    elif not all_terminal:
        new_status = "running"
    elif failed == total:
        new_status = "failed"
    elif success + cancelled == total and failed == 0:
        new_status = "success"
    else:
        new_status = "partial_success"

    now = datetime.now(timezone.utc)
    await db.execute(text("""
        UPDATE publish_batches SET status = :status, success_count = :sc,
        failed_count = :fc, cancelled_count = :cc, updated_at = :now
        WHERE id = :id
    """), {"status": new_status, "sc": success, "fc": failed, "cc": cancelled,
           "now": now, "id": bid})

    if new_status != batch_row.status:
        await write_publish_event(db, organization_id=batch_row.organization_id,
                                   brand_id=batch_row.brand_id,
                                   content_package_id=batch_row.content_package_id,
                                   publish_batch_id=bid,
                                   event_type="publish_batch_completed",
                                   old_status=batch_row.status, new_status=new_status,
                                   message=f"Batch {new_status}",
                                   created_by=actor_id)
    await db.flush()
    return {"status": new_status, "success": success, "failed": failed, "cancelled": cancelled}


async def update_cp_publish_summary(db: AsyncSession, content_package_id):
    """Recalculate ContentPackage publish_status_summary from active PublishRequests."""
    cid = _to_uuid(content_package_id)
    result = await db.execute(
        text("SELECT id FROM content_packages WHERE id = :id FOR UPDATE"), {"id": cid}
    )
    if not result.fetchone():
        return

    stats = (await db.execute(text("""
        SELECT status, COUNT(*) c FROM publish_requests
        WHERE content_package_id = :cid AND status NOT IN ('cancelled', 'archived')
        GROUP BY status
    """), {"cid": cid})).fetchall()

    published = failed = 0
    has_active = False
    for r in stats:
        if r.status in ("published",):
            published += r.c
        elif r.status in ("failed", "enqueue_failed", "rejected"):
            failed += r.c
        elif r.status not in ("revoked", "archived", "stale", "unknown", "delivered_no_callback"):
            has_active = True

    if published > 0 and not has_active:
        summary = "published"
    elif published > 0 and has_active:
        summary = "partially_published"
    elif has_active:
        summary = "publishing"
    elif failed > 0 and published == 0:
        summary = "failed"
    else:
        summary = "not_published"

    now = datetime.now(timezone.utc)
    await db.execute(text("""
        UPDATE content_packages SET publish_status_summary = :s,
        published_target_count = :pc, failed_target_count = :fc,
        last_published_at = CASE WHEN :s = 'published' THEN :now ELSE last_published_at END
        WHERE id = :id
    """), {"s": summary, "pc": published, "fc": failed, "now": now, "id": cid})
    await db.flush()


def _to_uuid(val):
    import uuid
    if isinstance(val, uuid.UUID):
        return val
    return uuid.UUID(str(val))
