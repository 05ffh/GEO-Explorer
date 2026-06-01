"""Publishing ViewModel — PublishTarget management, publish history (P2-4)."""
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.publishing.models import (PublishTarget, PublishBatch, PublishRequest,
                                    PublishAttempt, PublishEvent)


async def build_publishing_vm(organization_id, db: AsyncSession) -> dict:
    """Build view model for the publishing management page."""
    # Targets
    targets = (await db.execute(
        select(PublishTarget).where(
            PublishTarget.organization_id == organization_id,
            PublishTarget.status != "archived",
        ).order_by(desc(PublishTarget.created_at))
    )).scalars().all()

    # Recent requests
    requests = (await db.execute(
        select(PublishRequest).where(
            PublishRequest.organization_id == organization_id,
        ).order_by(desc(PublishRequest.created_at)).limit(30)
    )).scalars().all()

    # Recent batches
    batches = (await db.execute(
        select(PublishBatch).where(
            PublishBatch.organization_id == organization_id,
        ).order_by(desc(PublishBatch.created_at)).limit(10)
    )).scalars().all()

    # Health summary
    health_counts = {"healthy": 0, "degraded": 0, "failing": 0, "invalid": 0, "paused": 0}
    for t in targets:
        h = t.health_status or "healthy"
        health_counts[h] = health_counts.get(h, 0) + 1

    return {
        "targets": [_target_vm(t) for t in targets],
        "requests": [_request_vm(r) for r in requests],
        "batches": [_batch_vm(b) for b in batches],
        "health_summary": health_counts,
        "target_count": len(targets),
        "active_request_count": sum(1 for r in requests if r.status in ("queued", "sending")),
    }


def _target_vm(t: PublishTarget) -> dict:
    return {
        "id": str(t.id), "name": t.name, "target_type": t.target_type,
        "status": t.status, "health_status": t.health_status,
        "credential_status": t.credential_status,
        "endpoint_url": t.endpoint_url or "",
        "verified_at": t.verified_at.isoformat() if t.verified_at else None,
        "last_success_at": t.last_success_at.isoformat() if t.last_success_at else None,
        "last_failed_at": t.last_failed_at.isoformat() if t.last_failed_at else None,
        "failure_count": t.failure_count,
        "consecutive_failures": t.consecutive_failures,
        "circuit_breaker_state": t.circuit_breaker_state,
    }


def _request_vm(r: PublishRequest) -> dict:
    return {
        "id": str(r.id), "status": r.status, "publish_action": r.publish_action,
        "trigger_type": r.trigger_type,
        "external_edit_url": r.external_edit_url,
        "external_preview_url": r.external_preview_url,
        "external_public_url": r.external_public_url,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else "",
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "can_retry": r.status == "failed",
        "can_cancel": r.status in ("queued", "sending"),
    }


def _batch_vm(b: PublishBatch) -> dict:
    return {
        "id": str(b.id), "status": b.status,
        "total_targets": b.total_targets,
        "success_count": b.success_count,
        "failed_count": b.failed_count,
        "created_at": b.created_at.isoformat() if b.created_at else "",
    }
