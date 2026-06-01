"""Publishing delivery orchestrator — unified entry point for publish operations (P2-4)."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.publishing.models import (PublishTarget, PublishBatch, PublishRequest,
                                    PUBLISH_REQUEST_TRANSITIONS)
from src.publishing.payload_builder import build_publish_payload
from src.publishing.quality import check_publish_quality
from src.publishing.events import write_publish_event
from src.publishing.state_machine import (transition_publish_request, update_batch_status,
                                           update_cp_publish_summary)

logger = logging.getLogger(__name__)


async def create_publish_batch(db: AsyncSession, *, organization_id, brand_id,
                                content_package_id, target_ids: list,
                                trigger_type: str = "manual", requested_by=None,
                                force_republish: bool = False) -> dict:
    """Create a PublishBatch with PublishRequests for each target. Returns batch info."""
    # Validate content package
    cp = (await db.execute(
        text("SELECT * FROM content_packages WHERE id = :id FOR UPDATE"),
        {"id": content_package_id}
    )).fetchone()
    if not cp:
        return {"status": "error", "reason": "ContentPackage not found"}

    # Load targets
    targets = []
    for tid in target_ids:
        t = (await db.execute(
            select(PublishTarget).where(PublishTarget.id == tid)
        )).scalar_one_or_none()
        if t:
            targets.append(t)

    if not targets:
        return {"status": "error", "reason": "No valid targets"}

    # Cross-org check: all targets must belong to the organization
    for t in targets:
        if str(t.organization_id) != str(organization_id):
            return {"status": "error", "reason": "Target cross-org violation"}

    # Quality gate per target
    quality_results = {}
    for t in targets:
        qr = await check_publish_quality(cp, t, None, db)
        quality_results[str(t.id)] = qr

    active_targets = [t for t in targets if quality_results[str(t.id)]["passed"]]
    if not active_targets and not force_republish:
        return {"status": "error", "reason": "All targets failed quality gate",
                "quality": quality_results}

    targets_to_publish = targets if force_republish else active_targets

    # Create batch
    batch_id = uuid.uuid4()
    idempotency_key = _build_batch_idempotency_key(
        organization_id, brand_id, content_package_id,
        [str(t.id) for t in targets_to_publish], trigger_type
    )
    now = datetime.now(timezone.utc)

    try:
        await db.execute(text("""
            INSERT INTO publish_batches (id, organization_id, brand_id, content_package_id,
                trigger_type, requested_by, status, total_targets,
                publish_request_ids, idempotency_key, started_at, created_at, updated_at)
            VALUES (:id, :org, :bid, :cp, :trigger, :req_by, 'queued', :total,
                '[]', :ik, :now, :now, :now)
        """), {
            "id": batch_id, "org": organization_id, "bid": brand_id,
            "cp": content_package_id, "trigger": trigger_type, "req_by": requested_by,
            "total": len(targets_to_publish), "ik": idempotency_key, "now": now,
        })
    except Exception:
        # Idempotency key collision — return existing
        existing = (await db.execute(
            text("SELECT id, status FROM publish_batches WHERE idempotency_key = :ik"),
            {"ik": idempotency_key}
        )).fetchone()
        if existing:
            return {"status": "existing", "batch_id": str(existing.id),
                    "batch_status": existing.status}
        raise

    # Create PublishRequests
    request_ids = []
    request_results = []
    for t in targets_to_publish:
        req_id = uuid.uuid4()
        pr = await _create_publish_request(db, batch_id, organization_id, brand_id,
                                            content_package_id, t, trigger_type,
                                            requested_by, force_republish)
        request_ids.append(str(req_id))
        request_results.append(pr)

    # Update batch with request IDs
    import json
    await db.execute(text("""
        UPDATE publish_batches SET publish_request_ids = :ids, updated_at = :now WHERE id = :id
    """), {"ids": json.dumps(request_ids), "now": now, "id": batch_id})

    await write_publish_event(db, organization_id=organization_id, brand_id=brand_id,
                               content_package_id=content_package_id,
                               publish_batch_id=batch_id,
                               event_type="publish_requested",
                               message=f"Batch created with {len(targets_to_publish)} targets",
                               created_by=requested_by)
    await db.flush()

    # Enqueue async delivery for each request
    from src.publishing.tasks import publish_delivery_task
    enqueued = []
    for rid in request_ids:
        task = publish_delivery_task.delay(
            publish_request_id=str(rid),
            publish_batch_id=str(batch_id),
            webhook_secret="",  # Retrieved from target during execution
        )
        enqueued.append({"request_id": str(rid), "celery_task_id": task.id})

    return {
        "status": "created",
        "batch_id": str(batch_id),
        "total_targets": len(targets_to_publish),
        "request_ids": request_ids,
        "idempotency_key": idempotency_key,
        "quality": quality_results,
        "enqueued_tasks": enqueued,
    }


async def execute_publish_request(db: AsyncSession, request_id, webhook_secret: str = "",
                                   task_state_id: str | None = None) -> dict:
    """Execute a single PublishRequest — build payload, deliver webhook."""
    req = (await db.execute(
        text("SELECT * FROM publish_requests WHERE id = :id FOR UPDATE"),
        {"id": request_id}
    )).fetchone()
    if not req:
        return {"status": "error", "reason": "Request not found"}

    # Transition to sending
    ok = await transition_publish_request(db, request_id, "sending",
                                           message="Starting delivery")
    if not ok:
        return {"status": "error", "reason": "Cannot transition to sending"}

    # Load target
    target = (await db.execute(
        select(PublishTarget).where(PublishTarget.id == req.publish_target_id)
    )).scalar_one_or_none()
    if not target:
        await transition_publish_request(db, request_id, "failed",
                                          message="Target not found")
        return {"status": "error", "reason": "Target not found"}

    # Load content package
    cp = (await db.execute(
        text("SELECT * FROM content_packages WHERE id = :id"),
        {"id": req.content_package_id}
    )).fetchone()
    if not cp:
        await transition_publish_request(db, request_id, "failed",
                                          message="ContentPackage not found")
        return {"status": "error", "reason": "ContentPackage not found"}

    # Build payload
    cp_dict = dict(cp._mapping)
    target_dict = {
        "payload_version": target.payload_version,
        "auto_publish_on_approved": target.auto_publish_on_approved,
    }
    payload, payload_hash, callback_token = build_publish_payload(
        cp_dict, target_dict, str(request_id), req.publish_action
    )
    payload_hash_str = payload_hash if isinstance(payload_hash, str) else ""

    # Store payload hash
    await db.execute(text("""
        UPDATE publish_requests SET payload_hash = :hash WHERE id = :id
    """), {"hash": payload_hash_str, "id": request_id})

    # Determine channel and deliver
    if target.target_type == "webhook":
        from src.publishing.webhook import deliver_webhook
        result = await deliver_webhook(
            db, publish_request_id=str(request_id),
            publish_target_id=str(target.id),
            organization_id=str(req.organization_id),
            brand_id=str(req.brand_id),
            content_package_id=str(req.content_package_id),
            publish_batch_id=str(req.publish_batch_id),
            payload=payload, webhook_url=target.endpoint_url or "",
            webhook_secret=webhook_secret,
            attempt_no=1, task_state_id=task_state_id,
        )
    else:
        result = {"status": "error", "reason": f"Unsupported target_type: {target.target_type}"}

    # Update request status based on result
    if result.get("status") == "success":
        await transition_publish_request(db, request_id, "delivered",
                                          message="Webhook delivered successfully")
    elif result.get("status") == "failed" and not result.get("retryable"):
        await transition_publish_request(db, request_id, "failed",
                                          message=result.get("error_message", "Delivery failed"))
    elif result.get("status") == "failed" and result.get("retryable"):
        # Leave in sending for retry
        pass

    # Update batch and CP
    await update_batch_status(db, req.publish_batch_id)
    await update_cp_publish_summary(db, req.content_package_id)

    return {
        "status": result.get("status"),
        "request_id": str(request_id),
        "attempt": result,
    }


# ── Internal ──────────────────────────────────────────────────────────────────

async def _create_publish_request(db: AsyncSession, batch_id, org_id, brand_id,
                                   cp_id, target, trigger_type, requested_by,
                                   force_republish: bool) -> dict:
    """Create a single PublishRequest within a batch."""
    req_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    idempotency_key = _build_request_idempotency_key(
        org_id, brand_id, cp_id, target.id, trigger_type
    )

    try:
        await db.execute(text("""
            INSERT INTO publish_requests (id, organization_id, brand_id, content_package_id,
                publish_target_id, publish_batch_id, publish_action, trigger_type,
                requested_by, status, idempotency_key, review_required,
                force_republish, created_at, updated_at)
            VALUES (:id, :org, :bid, :cp, :tid, :batch, 'create', :trigger,
                :req_by, 'queued', :ik, true, :force, :now, :now)
        """), {
            "id": req_id, "org": org_id, "bid": brand_id, "cp": cp_id,
            "tid": target.id, "batch": batch_id, "trigger": trigger_type,
            "req_by": requested_by, "ik": idempotency_key,
            "force": force_republish, "now": now,
        })
    except Exception:
        existing = (await db.execute(
            text("SELECT id, status FROM publish_requests WHERE idempotency_key = :ik"),
            {"ik": idempotency_key}
        )).fetchone()
        if existing:
            return {"status": "existing", "request_id": str(existing.id)}
        raise

    await write_publish_event(db, organization_id=org_id, brand_id=brand_id,
                               content_package_id=cp_id, publish_batch_id=batch_id,
                               publish_request_id=req_id,
                               event_type="publish_requested",
                               message=f"PublishRequest created for target {target.id}",
                               created_by=requested_by)

    return {"status": "created", "request_id": str(req_id)}


def _build_batch_idempotency_key(org_id, brand_id, cp_id, target_ids: list, trigger: str) -> str:
    raw = f"{org_id}|{brand_id}|{cp_id}|{','.join(sorted(target_ids))}|{trigger}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _build_request_idempotency_key(org_id, brand_id, cp_id, target_id, trigger: str) -> str:
    raw = f"{org_id}|{brand_id}|{cp_id}|{target_id}|{trigger}"
    return hashlib.sha256(raw.encode()).hexdigest()
