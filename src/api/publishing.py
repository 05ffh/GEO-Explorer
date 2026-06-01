"""Publishing API endpoints — PublishTarget, PublishRequest, PublishBatch, Callback (P2-4)."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.publishing.models import (PublishTarget, PublishBatch, PublishRequest,
                                    PublishAttempt, PublishEvent)
from src.publishing.security import (generate_webhook_secret, hash_secret, mask_url,
                                      validate_webhook_url)
from src.publishing.delivery import create_publish_batch, execute_publish_request
from src.publishing.callbacks import process_callback
from src.publishing.state_machine import (transition_publish_request, update_batch_status,
                                           update_cp_publish_summary)
from src.publishing.pause import set_global_pause, set_org_pause, is_publishing_paused
from src.publishing.feature_flags import is_enabled

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/publishing", tags=["publishing"])


def _is_admin(user: User) -> bool:
    return user.has_permission("org:admin") if hasattr(user, "has_permission") else False


def _check_admin(user: User):
    if not _is_admin(user):
        raise HTTPException(403, "需要管理员权限")


# ── PublishTarget CRUD ────────────────────────────────────────────────────────

@router.get("/targets")
async def list_targets(request: Request, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db), status: str | None = None):
    """List PublishTargets for the current organization."""
    q = select(PublishTarget).where(PublishTarget.organization_id == user.organization_id)
    if status:
        q = q.where(PublishTarget.status == status)
    q = q.where(PublishTarget.status != "archived").order_by(desc(PublishTarget.created_at))
    result = await db.execute(q)
    targets = result.scalars().all()
    return [_target_response(t) for t in targets]


@router.post("/targets")
async def create_target(request: Request, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Create a new PublishTarget."""
    _check_admin(user)

    body = await request.json()
    name = body.get("name", "").strip()
    target_type = body.get("target_type", "webhook")
    endpoint_url = body.get("endpoint_url", "").strip()

    if not name:
        raise HTTPException(400, "name 不能为空")

    if target_type == "custom_rest":
        raise HTTPException(501, "Custom REST adapter 将在 Phase 3 支持")

    if target_type == "webhook" and endpoint_url:
        valid, err = validate_webhook_url(endpoint_url)
        if not valid:
            raise HTTPException(400, err)

    raw_secret = ""
    secret_hash = ""
    if target_type == "webhook":
        raw_secret = generate_webhook_secret()
        secret_hash = hash_secret(raw_secret)

    target = PublishTarget(
        organization_id=user.organization_id,
        brand_id=uuid.UUID(body["brand_id"]) if body.get("brand_id") else None,
        name=name,
        target_type=target_type,
        endpoint_url=endpoint_url,
        auth_type=body.get("auth_type"),
        webhook_secret_hash=secret_hash,
        cms_config=body.get("cms_config"),
        payload_version=body.get("payload_version", "2026-05"),
        is_default=body.get("is_default", False),
        created_by=user.id,
    )
    db.add(target)
    await db.flush()

    resp = _target_response(target)
    if raw_secret:
        resp["webhook_secret"] = raw_secret
    return resp


@router.patch("/targets/{target_id}")
async def update_target(target_id: str, request: Request,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Update a PublishTarget."""
    _check_admin(user)

    target = await db.get(PublishTarget, uuid.UUID(target_id))
    if not target:
        raise HTTPException(404, "PublishTarget not found")
    if str(target.organization_id) != str(user.organization_id):
        raise HTTPException(403, "跨组织访问被拒绝")

    body = await request.json()
    for field in ("name", "endpoint_url", "auth_type", "cms_config",
                  "payload_version", "is_default", "max_requests_per_minute",
                  "max_concurrent_requests"):
        if field in body:
            setattr(target, field, body[field])

    if "status" in body:
        target.status = body["status"]
    target.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return _target_response(target)


@router.post("/targets/{target_id}/verify")
async def verify_target(target_id: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Verify a PublishTarget connection."""
    target = await db.get(PublishTarget, uuid.UUID(target_id))
    if not target:
        raise HTTPException(404, "PublishTarget not found")
    if str(target.organization_id) != str(user.organization_id):
        raise HTTPException(403, "跨组织访问被拒绝")

    if target.endpoint_url:
        valid, err = validate_webhook_url(target.endpoint_url)
        if not valid:
            target.credential_status = "invalid"
            target.credential_error_code = "SSRF_BLOCKED"
            target.credential_last_checked_at = datetime.now(timezone.utc)
            await db.flush()
            return {"verified": False, "reason": err}

    if target.target_type == "webhook" and target.endpoint_url:
        try:
            import httpx
            challenge = str(uuid.uuid4())
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(target.endpoint_url, json={
                    "event": "publishing.target.verify",
                    "challenge": challenge,
                    "timestamp": int(datetime.now(timezone.utc).timestamp()),
                })
                if 200 <= resp.status_code < 300:
                    target.verified_at = datetime.now(timezone.utc)
                    target.credential_status = "valid"
                    target.credential_last_checked_at = datetime.now(timezone.utc)
                    target.consecutive_failures = 0
                    await db.flush()
                    return {"verified": True}
                else:
                    target.credential_status = "invalid"
                    target.credential_last_checked_at = datetime.now(timezone.utc)
                    target.credential_error_code = f"HTTP_{resp.status_code}"
                    await db.flush()
                    return {"verified": False, "reason": f"HTTP {resp.status_code}"}
        except Exception as e:
            target.credential_status = "invalid"
            target.credential_last_checked_at = datetime.now(timezone.utc)
            target.credential_error_code = "CONNECTION_FAILED"
            await db.flush()
            return {"verified": False, "reason": str(e)[:200]}

    return {"verified": False, "reason": "Unsupported target type"}


@router.post("/targets/{target_id}/rotate-secret")
async def rotate_secret(target_id: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Rotate webhook secret."""
    _check_admin(user)

    target = await db.get(PublishTarget, uuid.UUID(target_id))
    if not target:
        raise HTTPException(404, "PublishTarget not found")
    if str(target.organization_id) != str(user.organization_id):
        raise HTTPException(403, "跨组织访问被拒绝")

    target.previous_secret_hash = target.webhook_secret_hash
    raw = generate_webhook_secret()
    target.webhook_secret_hash = hash_secret(raw)
    target.secret_rotated_at = datetime.now(timezone.utc)
    await db.flush()

    return {"secret": raw}


@router.delete("/targets/{target_id}")
async def archive_target(target_id: str, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Archive (soft-delete) a PublishTarget."""
    _check_admin(user)

    target = await db.get(PublishTarget, uuid.UUID(target_id))
    if not target:
        raise HTTPException(404, "PublishTarget not found")
    if str(target.organization_id) != str(user.organization_id):
        raise HTTPException(403, "跨组织访问被拒绝")

    existing = (await db.execute(
        text("SELECT COUNT(*) c FROM publish_requests WHERE publish_target_id = :tid"),
        {"tid": target.id}
    )).scalar()
    if existing:
        target.status = "archived"
    else:
        await db.delete(target)
    await db.flush()
    return {"archived": True}


# ── PublishRequest / PublishBatch ─────────────────────────────────────────────

@router.post("/content-packages/{cp_id}/publish")
async def trigger_publish(cp_id: str, request: Request,
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """Trigger publishing a ContentPackage to one or more targets."""
    body = await request.json()
    target_ids = body.get("target_ids", [])
    if not target_ids:
        raise HTTPException(400, "target_ids 不能为空")
    force = body.get("force_republish", False)
    if force:
        _check_admin(user)

    result = await create_publish_batch(
        db, organization_id=user.organization_id,
        brand_id=body.get("brand_id", ""),
        content_package_id=uuid.UUID(cp_id),
        target_ids=[uuid.UUID(t) for t in target_ids],
        trigger_type="manual", requested_by=user.id,
        force_republish=force,
    )
    return result


@router.get("/requests/{request_id}")
async def get_publish_request(request_id: str, user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """Get PublishRequest details with events and attempts."""
    req = await db.get(PublishRequest, uuid.UUID(request_id))
    if not req:
        raise HTTPException(404, "PublishRequest not found")
    if str(req.organization_id) != str(user.organization_id):
        raise HTTPException(403, "跨组织访问被拒绝")

    events = (await db.execute(
        select(PublishEvent).where(PublishEvent.publish_request_id == req.id)
        .order_by(PublishEvent.created_at)
    )).scalars().all()

    attempts = (await db.execute(
        select(PublishAttempt).where(PublishAttempt.publish_request_id == req.id)
        .order_by(PublishAttempt.attempt_no)
    )).scalars().all()

    return {
        **_request_response(req),
        "events": [_event_response(e) for e in events],
        "attempts": [_attempt_response(a) for a in attempts],
    }


@router.get("/requests")
async def list_publish_requests(user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db),
                                 status: str | None = None, limit: int = 20, offset: int = 0):
    """List PublishRequests for the current organization."""
    q = select(PublishRequest).where(PublishRequest.organization_id == user.organization_id)
    if status:
        q = q.where(PublishRequest.status == status)
    q = q.order_by(desc(PublishRequest.created_at)).offset(offset).limit(limit)
    result = await db.execute(q)
    return [_request_response(r) for r in result.scalars().all()]


@router.post("/requests/{request_id}/cancel")
async def cancel_publish(request_id: str, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Cancel a queued or sending PublishRequest."""
    pr = await db.get(PublishRequest, uuid.UUID(request_id))
    if not pr:
        raise HTTPException(404, "PublishRequest not found")
    if str(pr.organization_id) != str(user.organization_id):
        raise HTTPException(403, "跨组织访问被拒绝")

    if pr.status == "queued":
        ok = await transition_publish_request(db, request_id, "cancelled",
                                               message="Cancelled by user", actor_id=user.id)
    elif pr.status == "sending":
        ok = await transition_publish_request(db, request_id, "cancel_requested",
                                               message="Cancel requested by user", actor_id=user.id)
    else:
        raise HTTPException(400, f"Cannot cancel request in status: {pr.status}")

    if not ok:
        raise HTTPException(409, "State transition failed")
    await update_batch_status(db, pr.publish_batch_id)
    return {"cancelled": True}


@router.post("/requests/{request_id}/retry")
async def retry_publish(request_id: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Manual retry a failed PublishRequest."""
    pr = await db.get(PublishRequest, uuid.UUID(request_id))
    if not pr:
        raise HTTPException(404, "PublishRequest not found")
    if str(pr.organization_id) != str(user.organization_id):
        raise HTTPException(403, "跨组织访问被拒绝")

    if pr.status != "failed":
        raise HTTPException(400, f"Can only retry failed requests, current: {pr.status}")

    ok = await transition_publish_request(db, request_id, "queued",
                                           message="Manual retry", actor_id=user.id)
    if not ok:
        raise HTTPException(409, "State transition failed")

    return {"retried": True, "request_id": str(pr.id)}


@router.get("/batches/{batch_id}")
async def get_publish_batch(batch_id: str, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """Get PublishBatch details."""
    batch = await db.get(PublishBatch, uuid.UUID(batch_id))
    if not batch:
        raise HTTPException(404, "PublishBatch not found")
    if str(batch.organization_id) != str(user.organization_id):
        raise HTTPException(403, "跨组织访问被拒绝")
    return _batch_response(batch)


@router.get("/batches")
async def list_publish_batches(user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db),
                                limit: int = 20, offset: int = 0):
    """List PublishBatches for the current organization."""
    q = select(PublishBatch).where(PublishBatch.organization_id == user.organization_id)
    q = q.order_by(desc(PublishBatch.created_at)).offset(offset).limit(limit)
    result = await db.execute(q)
    return [_batch_response(b) for b in result.scalars().all()]


# ── Pause & Feature Flags ────────────────────────────────────────────────────

@router.post("/pause")
async def pause_publishing(request: Request, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Global or org-level publishing pause (system_admin only)."""
    if user.platform_role not in ("system_owner", "system_admin"):
        raise HTTPException(403, "仅系统管理员可执行此操作")
    body = await request.json()
    scope = body.get("scope", "global")
    paused = body.get("paused", True)
    if scope == "global":
        return await set_global_pause(db, paused, actor_id=user.id)
    elif scope == "organization":
        org_id = body.get("organization_id", str(user.organization_id))
        return await set_org_pause(db, org_id, paused, actor_id=user.id)
    raise HTTPException(400, "Invalid scope")


@router.get("/pause/status")
async def get_pause_status(user: User = Depends(get_current_user)):
    """Check if publishing is currently paused."""
    is_paused, reason = is_publishing_paused(str(user.organization_id))
    return {"paused": is_paused, "reason": reason}


# ── Callback ──────────────────────────────────────────────────────────────────

@router.post("/callbacks")
async def receive_callback(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive a publish status callback from a customer system.
    Public endpoint — authenticated via HMAC + callback_token."""
    body = await request.json()
    headers = request.headers

    publish_request_id = body.get("publish_request_id", "")
    if not publish_request_id:
        raise HTTPException(400, "缺少 publish_request_id")

    result = await process_callback(
        db, publish_request_id=publish_request_id,
        callback_event_id=body.get("callback_event_id", str(uuid.uuid4())),
        callback_timestamp=int(body.get("timestamp", 0)),
        status=body.get("status", "received"),
        signature_header=headers.get("X-GEO-Callback-Signature", ""),
        callback_token=body.get("callback_token"),
        webhook_secret="",
        message=body.get("message", ""),
        external_id=body.get("external_id"),
        external_url=body.get("external_url"),
        payload=body,
    )
    return result


# ── Response helpers ──────────────────────────────────────────────────────────

def _target_response(t: PublishTarget) -> dict:
    return {
        "id": str(t.id), "name": t.name, "target_type": t.target_type,
        "status": t.status, "health_status": t.health_status,
        "credential_status": t.credential_status,
        "masked_endpoint_url": mask_url(t.endpoint_url or ""),
        "auth_type": t.auth_type,
        "payload_version": t.payload_version, "is_default": t.is_default,
        "circuit_breaker_state": t.circuit_breaker_state,
        "verified_at": t.verified_at.isoformat() if t.verified_at else None,
        "last_success_at": t.last_success_at.isoformat() if t.last_success_at else None,
        "last_failed_at": t.last_failed_at.isoformat() if t.last_failed_at else None,
        "failure_count": t.failure_count,
        "consecutive_failures": t.consecutive_failures,
        "can_edit": True,
    }


def _request_response(r: PublishRequest) -> dict:
    return {
        "id": str(r.id), "status": r.status, "publish_action": r.publish_action,
        "content_package_id": str(r.content_package_id),
        "publish_target_id": str(r.publish_target_id),
        "publish_batch_id": str(r.publish_batch_id),
        "trigger_type": r.trigger_type,
        "external_id": r.external_id,
        "external_edit_url": r.external_edit_url,
        "external_preview_url": r.external_preview_url,
        "external_public_url": r.external_public_url,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "can_retry": r.status == "failed",
        "can_cancel": r.status in ("queued", "sending"),
    }


def _attempt_response(a: PublishAttempt) -> dict:
    return {
        "attempt_no": a.attempt_no, "status": a.status, "channel": a.channel,
        "response_status_code": a.response_status_code,
        "error_code": a.error_code, "error_category": a.error_category,
        "retryable": a.retryable,
        "sent_at": a.sent_at.isoformat() if a.sent_at else None,
        "next_retry_at": a.next_retry_at.isoformat() if a.next_retry_at else None,
    }


def _event_response(e: PublishEvent) -> dict:
    return {
        "event_type": e.event_type, "old_status": e.old_status,
        "new_status": e.new_status, "message": e.message,
        "created_at": e.created_at.isoformat() if e.created_at else "",
    }


def _batch_response(b: PublishBatch) -> dict:
    return {
        "id": str(b.id), "status": b.status,
        "content_package_id": str(b.content_package_id),
        "trigger_type": b.trigger_type,
        "total_targets": b.total_targets,
        "success_count": b.success_count,
        "failed_count": b.failed_count,
        "cancelled_count": b.cancelled_count,
        "started_at": b.started_at.isoformat() if b.started_at else None,
        "completed_at": b.completed_at.isoformat() if b.completed_at else None,
        "created_at": b.created_at.isoformat() if b.created_at else "",
    }
