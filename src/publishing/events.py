"""Publish events — write lifecycle events for the publishing system (P2-4)."""
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def write_publish_event(db: AsyncSession, *, organization_id, brand_id=None,
                               content_package_id=None, publish_batch_id=None,
                               publish_request_id=None, publish_attempt_id=None,
                               event_type: str, old_status: str | None = None,
                               new_status: str | None = None, message: str = "",
                               metadata_json: dict | None = None, created_by=None) -> str:
    """Write a PublishEvent and return the event ID."""
    import uuid
    event_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    await db.execute(text("""
        INSERT INTO publish_events (id, organization_id, brand_id, content_package_id,
            publish_batch_id, publish_request_id, publish_attempt_id,
            event_type, old_status, new_status, message, metadata_json,
            created_by, created_at)
        VALUES (:id, :org, :bid, :cp_id, :batch_id, :req_id, :att_id,
            :event_type, :old_status, :new_status, :message, :meta,
            :created_by, :now)
    """), {
        "id": event_id, "org": organization_id, "bid": brand_id,
        "cp_id": content_package_id, "batch_id": publish_batch_id,
        "req_id": publish_request_id, "att_id": publish_attempt_id,
        "event_type": event_type, "old_status": old_status,
        "new_status": new_status, "message": message,
        "meta": metadata_json or {}, "created_by": created_by, "now": now,
    })
    await db.flush()
    return str(event_id)
