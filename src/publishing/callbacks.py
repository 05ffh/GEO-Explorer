"""Publishing callbacks — handle incoming status callbacks from customer systems (P2-4)."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.publishing.security import (verify_hmac_signature, verify_callback_timestamp,
                                      hash_secret)
from src.publishing.events import write_publish_event
from src.publishing.state_machine import transition_publish_request

logger = logging.getLogger(__name__)

CALLBACK_TOKEN_EXPIRY_HOURS = 72


async def process_callback(db: AsyncSession, *, publish_request_id: str,
                            callback_event_id: str, callback_timestamp: int,
                            status: str, signature_header: str | None = None,
                            callback_token: str | None = None,
                            webhook_secret: str = "", message: str = "",
                            external_id: str | None = None,
                            external_url: str | None = None,
                            payload: dict | None = None) -> dict:
    """Process an incoming publish status callback. Returns result dict."""

    # 1. Check timestamp window
    if not verify_callback_timestamp(callback_timestamp):
        logger.warning(f"Callback timestamp outside window: {callback_timestamp}")
        return {"status": "rejected", "reason": "timestamp_outside_window"}

    # 2. Check replay (callback_event_id unique constraint in DB)
    existing = (await db.execute(text(
        "SELECT id FROM publish_status_callbacks WHERE callback_event_id = :eid"
    ), {"eid": callback_event_id})).fetchone()
    if existing:
        # Record replay
        await db.execute(text("""
            UPDATE publish_status_callbacks SET replay_detected = true
            WHERE callback_event_id = :eid
        """), {"eid": callback_event_id})
        return {"status": "replay_detected", "reason": "duplicate_event_id"}

    # 3. Verify HMAC signature
    body = payload or {}
    import json
    body_bytes = json.dumps(body, ensure_ascii=False).encode() if body else b"{}"
    sig_valid = False
    if signature_header and webhook_secret:
        sig_valid = verify_hmac_signature(body_bytes, webhook_secret,
                                           str(callback_timestamp), signature_header)

    # 4. Verify callback token
    token_valid = False
    token_hash = ""
    if callback_token:
        token_hash = hashlib.sha256(callback_token.encode()).hexdigest()
        token_row = (await db.execute(text(
            "SELECT callback_token_hash, callback_token_expires_at, callback_token_used_at "
            "FROM publish_status_callbacks WHERE publish_request_id = :rid "
            "ORDER BY created_at DESC LIMIT 1"
        ), {"rid": publish_request_id})).fetchone()
        if token_row:
            stored_hash = token_row.callback_token_hash
            if token_hash == stored_hash:
                if token_row.callback_token_used_at is None:
                    now = datetime.now(timezone.utc)
                    if token_row.callback_token_expires_at and now <= token_row.callback_token_expires_at:
                        token_valid = True

    # 5. Write callback record
    cb_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now  # fallback
    await db.execute(text("""
        INSERT INTO publish_status_callbacks (id, publish_request_id, publish_target_id,
            callback_token_hash, callback_event_id, callback_timestamp,
            callback_token_expires_at, callback_token_used_at,
            external_id, external_url, status, message,
            callback_payload, signature_header, signature_valid,
            token_valid, replay_detected, processed, received_at, created_at)
        VALUES (:id, :rid, (SELECT publish_target_id FROM publish_requests WHERE id = :rid2),
            :tok_hash, :eid, :ts, :expires, :used_at,
            :ext_id, :ext_url, :status, :msg,
            :payload, :sig_hdr, :sig_valid, :tok_valid,
            false, false, :now, :now)
    """), {
        "id": cb_id, "rid": publish_request_id, "rid2": publish_request_id,
        "tok_hash": token_hash, "eid": callback_event_id,
        "ts": datetime.fromtimestamp(callback_timestamp, tz=timezone.utc),
        "expires": expires_at,
        "used_at": now if token_valid else None,
        "ext_id": external_id, "ext_url": external_url,
        "status": status, "msg": message,
        "payload": payload or {},
        "sig_hdr": signature_header, "sig_valid": sig_valid,
        "tok_valid": token_valid, "now": now,
    })

    # Mark token as used
    if token_valid:
        await db.execute(text("""
            UPDATE publish_status_callbacks SET callback_token_used_at = :now,
            processed = true WHERE id = :id
        """), {"now": now, "id": cb_id})

    # 6. Transition PublishRequest if valid
    if sig_valid and token_valid:
        # Map callback status to PublishRequest status
        status_map = {
            "received": "acknowledged",
            "accepted": "acknowledged",
            "draft_created": "draft_created",
            "published": "published",
            "failed": "failed",
            "rejected": "rejected",
        }
        new_request_status = status_map.get(status)
        if new_request_status:
            success = await transition_publish_request(
                db, publish_request_id, new_request_status,
                message=f"Callback: {status}",
                metadata={"callback_event_id": callback_event_id},
            )
            if not success:
                await db.execute(text("""
                    UPDATE publish_status_callbacks SET processing_error = '状态转移被拒'
                    WHERE id = :id
                """), {"id": cb_id})
        else:
            await db.execute(text("""
                UPDATE publish_status_callbacks SET processing_error = '未知回调状态'
                WHERE id = :id
            """), {"id": cb_id})
    else:
        await db.execute(text("""
            UPDATE publish_status_callbacks SET processing_error =
            CASE WHEN :sv = false THEN 'HMAC signature invalid'
                 WHEN :tv = false THEN 'Callback token invalid'
                 ELSE 'unknown' END
            WHERE id = :id
        """), {"sv": sig_valid, "tv": token_valid, "id": cb_id})

    # Write event
    req_row = (await db.execute(text(
        "SELECT organization_id, brand_id, content_package_id FROM publish_requests WHERE id = :rid"
    ), {"rid": publish_request_id})).fetchone()
    if req_row:
        await write_publish_event(db, organization_id=req_row.organization_id,
                                   brand_id=req_row.brand_id,
                                   content_package_id=req_row.content_package_id,
                                   publish_request_id=uuid.UUID(publish_request_id),
                                   event_type="publish_callback_received",
                                   message=f"Callback: {status} (valid={sig_valid and token_valid})",
                                   metadata_json={"callback_event_id": callback_event_id,
                                                  "status": status})

    await db.flush()
    return {"status": "processed" if sig_valid and token_valid else "rejected",
            "callback_id": str(cb_id)}
