"""Queue alerts — scope-aware dedup, upgrade, auto-resolve."""
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy import select, update, and_
from src.config import settings
from src.models.queue_alert import QueueAlert
from src.database import async_session_factory

logger = logging.getLogger(__name__)

ALERT_TYPES = {
    "queue_backlog_high": {"severity": "warning", "message_tpl": "队列积压: {value} > {threshold}"},
    "dlq_backlog_high": {"severity": "warning", "message_tpl": "DLQ积压: {value} > {threshold}"},
    "worker_offline": {"severity": "critical", "message_tpl": "Worker离线"},
    "retry_spike": {"severity": "warning", "message_tpl": "重试率异常: {value:.1%} > {threshold:.1%}"},
    "task_failure_rate_high": {"severity": "critical", "message_tpl": "失败率异常: {value:.1%} > {threshold:.1%}"},
    "platform_circuit_open": {"severity": "critical", "message_tpl": "平台熔断: {platform}"},
    "task_timeout_spike": {"severity": "warning", "message_tpl": "超时率异常: {value:.1%} > {threshold:.1%}"},
}


def _build_dedupe_key(alert_type: str, severity: str, org_id: str | None,
                      queue_name: str | None, platform: str | None) -> str:
    bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    parts = [alert_type, severity, org_id or "_", queue_name or "_", platform or "_", bucket]
    return ":".join(str(p) for p in parts)


async def create_or_update_alert(*, alert_type: str, severity: str | None = None,
                                  org_id: uuid.UUID | None = None,
                                  queue_name: str | None = None,
                                  platform: str | None = None,
                                  current_value: float | None = None,
                                  threshold: float | None = None,
                                  message: str = "") -> QueueAlert | None:
    """Create or update a queue alert with dedup. Returns alert or None if suppressed."""
    cfg = ALERT_TYPES.get(alert_type, {})
    sev = severity or cfg.get("severity", "warning")
    msg = message or cfg.get("message_tpl", "").format(
        value=current_value, threshold=threshold, platform=platform or "",
    )
    dedupe_key = _build_dedupe_key(alert_type, sev, str(org_id) if org_id else None,
                                    queue_name, platform)

    async with async_session_factory() as db:
        # Check existing
        existing = (await db.execute(
            select(QueueAlert).where(QueueAlert.dedupe_key == dedupe_key)
        )).scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if existing:
            # Update
            existing.current_value = current_value
            existing.last_seen_at = now
            existing.message = msg
            await db.commit()
            return existing

        # Check for upgrade: existing warning + new critical
        if sev == "critical":
            warn_key = _build_dedupe_key(alert_type, "warning",
                                          str(org_id) if org_id else None,
                                          queue_name, platform)
            warn_existing = (await db.execute(
                select(QueueAlert).where(
                    QueueAlert.dedupe_key == warn_key,
                    QueueAlert.status == "open",
                )
            )).scalar_one_or_none()
            if warn_existing:
                # Upgrade to critical
                warn_existing.severity = "critical"
                warn_existing.current_value = current_value
                warn_existing.last_seen_at = now
                warn_existing.message = msg
                warn_existing.dedupe_key = dedupe_key
                await db.commit()
                return warn_existing

        # Create new
        alert = QueueAlert(
            organization_id=org_id,
            queue_name=queue_name,
            platform=platform,
            alert_type=alert_type,
            severity=sev,
            current_value=current_value,
            threshold=threshold,
            message=msg,
            status="open",
            dedupe_key=dedupe_key,
            last_seen_at=now,
        )
        db.add(alert)
        await db.commit()
        await db.refresh(alert)
        logger.info(f"QueueAlert created: {alert_type} [{sev}] — {msg}")
        return alert


async def resolve_alerts_for_metric(*, alert_type: str, org_id: uuid.UUID | None = None,
                                     queue_name: str | None = None,
                                     platform: str | None = None):
    """Auto-resolve open alerts when metric recovers."""
    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)
        conditions = [
            QueueAlert.alert_type == alert_type,
            QueueAlert.status == "open",
        ]
        if org_id:
            conditions.append(QueueAlert.organization_id == org_id)
        if queue_name:
            conditions.append(QueueAlert.queue_name == queue_name)
        if platform:
            conditions.append(QueueAlert.platform == platform)

        stmt = (
            update(QueueAlert)
            .where(and_(*conditions))
            .values(status="resolved", resolved_at=now)
        )
        result = await db.execute(stmt)
        if result.rowcount:
            await db.commit()
            logger.info(f"Auto-resolved {result.rowcount} alerts for {alert_type}")
