"""Task control & queue monitoring API (P1-5)."""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from src.database import get_db
from src.api.deps import get_current_user, require_permission
from src.models.user import User
from src.models.task_state import TaskState, TaskEvent
from src.models.queue_alert import QueueAlert
from src.celery_app import app

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _task_response(ts: TaskState, user_is_admin: bool = False) -> dict:
    """Standardized task status response."""
    return {
        "task_id": ts.celery_task_id,
        "root_task_id": ts.root_task_id,
        "parent_task_state_id": str(ts.parent_task_state_id) if ts.parent_task_state_id else None,
        "task_name": ts.task_name,
        "status": ts.status,
        "progress": ts.progress,
        "progress_message": ts.progress_message,
        "retry_count": ts.retry_count,
        "max_retries": ts.max_retries,
        "collection_run_id": str(ts.collection_run_id) if ts.collection_run_id else None,
        "can_cancel": ts.status in ("queued", "running", "retrying"),
        "can_requeue": ts.status == "dead_lettered" and ts.dlq_retry_policy in ("auto", "manual"),
        "error": {
            "type": ts.error_type,
            "message": ts.error_message,
            "traceback": ts.error_traceback if user_is_admin else None,
        } if ts.error_type else None,
        "timestamps": {
            "queued_at": ts.queued_at.isoformat() if ts.queued_at else None,
            "started_at": ts.started_at.isoformat() if ts.started_at else None,
            "completed_at": ts.completed_at.isoformat() if ts.completed_at else None,
            "next_retry_at": ts.next_retry_at.isoformat() if ts.next_retry_at else None,
        },
    }


# ── Task status ─────────────────────────────────────────────────────────────

@router.get("/{task_id}")
async def get_task_status(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Query task progress. Frontend polls this for real-time status."""
    ts = (await db.execute(
        select(TaskState).where(
            TaskState.celery_task_id == task_id,
            TaskState.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not ts:
        raise HTTPException(404, "Task not found")
    is_admin = user.has_permission("org:admin") if hasattr(user, "has_permission") else False
    return _task_response(ts, user_is_admin=is_admin)


@router.get("/brand/{brand_id}")
async def list_brand_tasks(
    brand_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tasks for a brand with pagination and filtering."""
    conditions = [
        TaskState.brand_id == uuid.UUID(brand_id),
        TaskState.organization_id == user.organization_id,
    ]
    if status:
        conditions.append(TaskState.status == status)

    q = select(TaskState).where(and_(*conditions)).order_by(desc(TaskState.created_at))
    q = q.offset((page - 1) * page_size).limit(page_size)
    results = (await db.execute(q)).scalars().all()

    count_q = select(func.count(TaskState.id)).where(and_(*conditions))
    total = (await db.execute(count_q)).scalar()

    is_admin = user.has_permission("org:admin") if hasattr(user, "has_permission") else False
    return {
        "items": [_task_response(ts, is_admin) for ts in results],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


# ── Task control ────────────────────────────────────────────────────────────

@router.post("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a task — revoke for queued, cooperative signal for running."""
    ts = (await db.execute(
        select(TaskState).where(
            TaskState.celery_task_id == task_id,
            TaskState.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not ts:
        raise HTTPException(404, "Task not found")
    if ts.status not in ("queued", "running", "retrying"):
        return {
            "task_id": task_id,
            "action": "cancel",
            "accepted": False,
            "message": f"无法取消状态为 {ts.status} 的任务",
        }

    from src.queue.control import cancel_task as do_cancel
    result = await do_cancel(task_id, ts.status, terminate=False)
    if result["accepted"]:
        ts.control_action = "cancel"
        ts.requested_by = user.id
        if ts.status == "queued":
            ts.status = "cancelled"
        await db.commit()

        # Audit
        from src.services.audit import add_audit_log
        await add_audit_log(
            db, organization_id=user.organization_id, user_id=user.id,
            action="task_cancelled",
            target_type="task_state",
            target_id=str(ts.id),
            detail=f"Task {task_id} cancelled via {result['mechanism']}",
        )
        await db.commit()

    return {"task_id": task_id, "action": "cancel", **result}


@router.post("/{task_id}/force-terminate")
async def force_terminate_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force terminate — system_owner only."""
    from src.api.deps import require_platform_permission
    await require_platform_permission("platform:task_force_terminate", user)

    ts = (await db.execute(
        select(TaskState).where(TaskState.celery_task_id == task_id)
    )).scalar_one_or_none()
    if not ts:
        raise HTTPException(404, "Task not found")

    from src.queue.control import cancel_task as do_cancel
    result = await do_cancel(task_id, ts.status, terminate=True)
    if result["accepted"]:
        ts.status = "cancelled"
        ts.control_action = "cancel"

        from src.services.audit import add_audit_log
        await add_audit_log(
            db, organization_id=ts.organization_id, user_id=user.id,
            action="task_force_terminated",
            target_type="task_state",
            target_id=str(ts.id),
            detail=f"FORCE TERMINATE: {task_id}",
        )
        await db.commit()

    return {"task_id": task_id, "action": "force_terminate", **result}


# ── DLQ management ──────────────────────────────────────────────────────────

@router.post("/dlq/{task_state_id}/requeue")
async def requeue_dlq_task(
    task_state_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually requeue a DLQ task."""
    ts = await db.get(TaskState, uuid.UUID(task_state_id))
    if not ts:
        raise HTTPException(404, "Task not found")
    if ts.status != "dead_lettered":
        raise HTTPException(400, f"Task is not in DLQ: {ts.status}")

    from src.queue.dlq import requeue_dlq_task as do_requeue
    new_ts = await do_requeue(ts)
    if not new_ts:
        raise HTTPException(500, "Requeue failed — unknown task type")

    from src.services.audit import add_audit_log
    await add_audit_log(
        db, organization_id=user.organization_id, user_id=user.id,
        action="task_requeued",
        target_type="task_state",
        target_id=str(ts.id),
        detail=f"DLQ requeue: {ts.celery_task_id} -> {new_ts.celery_task_id}",
    )
    await db.commit()

    return {
        "original_task_id": ts.celery_task_id,
        "new_task_id": new_ts.celery_task_id,
        "status": "requeued",
    }


@router.patch("/dlq/{task_state_id}/mark-terminal")
async def mark_dlq_terminal(
    task_state_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a DLQ task as permanently failed (never retry)."""
    ts = await db.get(TaskState, uuid.UUID(task_state_id))
    if not ts:
        raise HTTPException(404, "Task not found")

    from src.queue.dlq import mark_dlq_terminal as do_mark
    await do_mark(ts)

    from src.services.audit import add_audit_log
    await add_audit_log(
        db, organization_id=user.organization_id, user_id=user.id,
        action="dlq_marked_terminal",
        target_type="task_state",
        target_id=str(ts.id),
        detail=f"DLQ marked terminal: {ts.celery_task_id}",
    )
    await db.commit()

    return {"task_id": ts.celery_task_id, "status": "terminal"}


# ── Queue monitoring ────────────────────────────────────────────────────────

@router.get("/queue/summary")
async def get_queue_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue monitoring summary — TaskState-based metrics."""
    is_platform = hasattr(user, "platform_role") and user.platform_role in (
        "system_owner", "system_admin", "system_operator",
    )

    org_filter = [] if is_platform else [TaskState.organization_id == user.organization_id]

    async def _count(status: str) -> int:
        conditions = [TaskState.status == status] + org_filter
        result = await db.execute(select(func.count(TaskState.id)).where(and_(*conditions)))
        return result.scalar() or 0

    queued = await _count("queued")
    running = await _count("running")
    retrying = await _count("retrying")
    dlq_count = await _count("dead_lettered")

    # Celery inspect (best-effort)
    celery_info = {"active_count": 0, "online_count": 0}
    try:
        insp = app.control.inspect()
        active = insp.active()
        if active:
            celery_info["online_count"] = len(active)
            celery_info["active_count"] = sum(len(v) for v in active.values())
    except Exception:
        pass

    # DLQ breakdown
    dlq_auto = (await db.execute(
        select(func.count(TaskState.id)).where(
            TaskState.status == "dead_lettered",
            TaskState.dlq_retry_policy == "auto",
            *org_filter,
        )
    )).scalar() or 0
    dlq_manual = (await db.execute(
        select(func.count(TaskState.id)).where(
            TaskState.status == "dead_lettered",
            TaskState.dlq_retry_policy == "manual",
            *org_filter,
        )
    )).scalar() or 0
    dlq_never = (await db.execute(
        select(func.count(TaskState.id)).where(
            TaskState.status == "dead_lettered",
            TaskState.dlq_retry_policy == "never",
            *org_filter,
        )
    )).scalar() or 0

    # Platform health
    from src.queue.circuit_breaker import get_all_health
    platform_health = await get_all_health()

    # Open alerts
    alert_conditions = [QueueAlert.status == "open"]
    if not is_platform:
        alert_conditions.append(QueueAlert.organization_id == user.organization_id)
    open_alerts = (await db.execute(
        select(QueueAlert).where(and_(*alert_conditions))
    )).scalars().all()

    return {
        "scope": "platform" if is_platform else "organization",
        "queue_metrics": {
            "queued_count": queued,
            "running_count": running,
            "retrying_count": retrying,
            "dead_lettered_count": dlq_count,
        },
        "worker_metrics": celery_info,
        "dlq_metrics": {
            "total": dlq_count,
            "auto_retriable": dlq_auto,
            "manual_review": dlq_manual,
            "terminal": dlq_never,
        },
        "platform_health": platform_health,
        "alerts": [
            {"id": str(a.id), "type": a.alert_type, "severity": a.severity,
             "message": a.message, "status": a.status}
            for a in (open_alerts or [])
        ],
    }


@router.get("/platform/health")
async def get_platform_health(
    user: User = Depends(get_current_user),
):
    """Get platform health (circuit breaker status)."""
    from src.queue.circuit_breaker import get_all_health
    return await get_all_health()
