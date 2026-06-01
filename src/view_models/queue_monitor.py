"""Queue monitor ViewModel — pre-compute display values for queue monitoring page."""
from sqlalchemy import select, func, desc, and_
from src.models.task_state import TaskState
from src.models.queue_alert import QueueAlert


async def build_queue_monitor_vm(brand, user, db) -> dict:
    """Build view model for the queue monitor page."""
    org_id = user.organization_id
    is_platform = hasattr(user, "platform_role") and user.platform_role in (
        "system_owner", "system_admin", "system_operator",
    )

    org_filter = [] if is_platform else [TaskState.organization_id == org_id]

    async def _count(status: str) -> int:
        conditions = [TaskState.status == status] + org_filter
        r = await db.execute(select(func.count(TaskState.id)).where(and_(*conditions)))
        return r.scalar() or 0

    # Counts
    queued = await _count("queued")
    running = await _count("running")
    retrying = await _count("retrying")
    completed_24h = await _count("completed")  # approximate
    failed = await _count("failed")
    dlq_count = await _count("dead_lettered")

    # Recent tasks
    conditions = org_filter.copy()
    r = await db.execute(
        select(TaskState).where(and_(*conditions))
        .order_by(desc(TaskState.created_at)).limit(20)
    )
    recent = r.scalars().all()

    # DLQ tasks
    dlq_conditions = [TaskState.status == "dead_lettered"] + org_filter
    r = await db.execute(
        select(TaskState).where(and_(*dlq_conditions))
        .order_by(desc(TaskState.dlq_at)).limit(50)
    )
    dlq_tasks = r.scalars().all()

    # Open alerts
    alert_conditions = [QueueAlert.status == "open"]
    if not is_platform:
        alert_conditions.append(QueueAlert.organization_id == org_id)
    r = await db.execute(
        select(QueueAlert).where(and_(*alert_conditions))
        .order_by(desc(QueueAlert.created_at)).limit(20)
    )
    alerts = r.scalars().all()

    # Platform health
    from src.queue.circuit_breaker import get_all_health
    platform_health = await get_all_health()

    return {
        "brand": {"id": str(brand.id) if brand else "", "name": brand.name if brand else "全品牌"},
        "counts": {
            "queued": queued, "running": running, "retrying": retrying,
            "completed": completed_24h, "failed": failed, "dead_lettered": dlq_count,
        },
        "recent_tasks": [
            {
                "task_id": t.celery_task_id,
                "task_name": t.task_name.rsplit(".", 1)[-1] if t.task_name else "",
                "status": t.status,
                "progress": t.progress,
                "progress_message": t.progress_message,
                "error_type": t.error_type,
                "retry_count": t.retry_count,
                "created_at": t.created_at.isoformat() if t.created_at else "",
            }
            for t in recent
        ],
        "dlq_tasks": [
            {
                "id": str(t.id),
                "task_id": t.celery_task_id,
                "task_name": t.task_name.rsplit(".", 1)[-1] if t.task_name else "",
                "dlq_retry_policy": t.dlq_retry_policy,
                "dlq_reason": t.dlq_reason,
                "dlq_requeue_count": t.dlq_requeue_count,
                "dlq_max_requeues": t.dlq_max_requeues,
                "dlq_at": t.dlq_at.isoformat() if t.dlq_at else "",
                "error_type": t.error_type,
            }
            for t in dlq_tasks
        ],
        "alerts": [
            {
                "id": str(a.id), "alert_type": a.alert_type, "severity": a.severity,
                "message": a.message, "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else "",
            }
            for a in alerts
        ],
        "platform_health": platform_health,
        "is_platform": is_platform,
    }
