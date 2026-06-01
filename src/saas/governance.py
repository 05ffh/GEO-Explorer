"""SaaS governance Celery tasks — reconciliation, retention, cleanup (P2-5)."""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.celery_app import app as celery_app
from src.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def _run_async(coro):
    return asyncio.run(coro)


# ── P2-4 Publishing Reconciliation ────────────────────────────────────────────

@celery_app.task(name="src.publishing.reconciliation.reconcile_publish_requests_task")
def reconcile_publish_requests_task():
    async def run():
        async with SessionLocal() as db:
            from src.publishing.reconciliation import reconcile_publish_requests
            return await reconcile_publish_requests(db)
    return _run_async(run())


@celery_app.task(name="src.publishing.reconciliation.reconcile_publish_batches_task")
def reconcile_publish_batches_task():
    async def run():
        async with SessionLocal() as db:
            from src.publishing.reconciliation import reconcile_publish_batches
            return await reconcile_publish_batches(db)
    return _run_async(run())


@celery_app.task(name="src.publishing.reconciliation.reconcile_publish_targets_task")
def reconcile_publish_targets_task():
    async def run():
        async with SessionLocal() as db:
            from src.publishing.reconciliation import reconcile_publish_targets
            return await reconcile_publish_targets(db)
    return _run_async(run())


# ── P2-5 SaaS Governance ─────────────────────────────────────────────────────

@celery_app.task(name="src.saas.governance.reconcole_org_usage_counts_task")
def reconcole_org_usage_counts_task():
    async def run():
        async with SessionLocal() as db:
            from src.saas.quota import reconcole_org_usage_counts
            orgs = (await db.execute(text(
                "SELECT id FROM organizations WHERE is_active = true"
            ))).fetchall()
            count = 0
            for org in orgs:
                await reconcole_org_usage_counts(db, org.id)
                count += 1
            await db.commit()
            return {"reconciled_orgs": count}
    return _run_async(run())


@celery_app.task(name="src.saas.governance.aggregate_usage_snapshots_task")
def aggregate_usage_snapshots_task():
    async def run():
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            orgs = (await db.execute(text(
                "SELECT id FROM organizations WHERE is_active = true"
            ))).fetchall()
            count = 0
            for org in orgs:
                # Check if snapshot already exists for this period
                existing = (await db.execute(text(
                    "SELECT id FROM usage_snapshots WHERE organization_id = :oid "
                    "AND period_start = :ps AND snapshot_type = 'customer'"
                ), {"oid": org.id, "ps": period_start})).fetchone()
                if existing:
                    continue

                # Count usage events for this period
                stats = (await db.execute(text("""
                    SELECT meter_key, SUM(quantity) as total
                    FROM usage_events
                    WHERE organization_id = :oid AND occurred_at >= :ps
                    GROUP BY meter_key
                """), {"oid": org.id, "ps": period_start})).fetchall()

                meter_totals = {r.meter_key: float(r.total or 0) for r in stats}

                await db.execute(text("""
                    INSERT INTO usage_snapshots (id, organization_id, snapshot_type,
                        period_start, period_end, period_timezone, period_type,
                        collection_runs, api_requests, token_usage, report_count,
                        export_count, storage_mb, created_at, updated_at)
                    VALUES (gen_random_uuid(), :oid, 'customer', :ps, :pe, 'UTC', 'monthly',
                        :col, :api, :tok, :rep, :exp, 0, :now, :now)
                """), {
                    "oid": org.id, "ps": period_start,
                    "pe": now, "now": now,
                    "col": int(meter_totals.get("collection_runs_per_month", 0)),
                    "api": int(meter_totals.get("api_requests_per_month", 0)),
                    "tok": int(meter_totals.get("token_usage", 0)),
                    "rep": int(meter_totals.get("reports_per_month", 0)),
                    "exp": int(meter_totals.get("exports_per_month", 0)),
                })
                count += 1
            await db.commit()
            return {"aggregated_orgs": count}
    return _run_async(run())


@celery_app.task(name="src.saas.governance.enforce_data_retention_task")
def enforce_data_retention_task():
    async def run():
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            # Get retention days from active subscriptions
            subs = (await db.execute(text("""
                SELECT s.organization_id,
                       COALESCE(p.data_retention_days, 90) as retention_days
                FROM org_subscriptions s
                JOIN plan_definitions p ON s.plan_id = p.id
                WHERE s.status IN ('active', 'trialing', 'grace')
            """))).fetchall()

            cleaned = 0
            for sub in subs:
                cutoff = now - timedelta(days=sub.retention_days if sub.retention_days > 0 else 36500)
                # Clean old collection data
                for tbl in ["query_results", "hallucination_results", "metrics_snapshots"]:
                    result = await db.execute(text(
                        f"DELETE FROM {tbl} WHERE organization_id = :oid AND created_at < :cutoff"
                    ), {"oid": sub.organization_id, "cutoff": cutoff})
                    cleaned += result.rowcount or 0
            await db.commit()
            return {"cleaned_rows": cleaned}
    return _run_async(run())


@celery_app.task(name="src.saas.governance.cleanup_expired_exports_task")
def cleanup_expired_exports_task():
    async def run():
        async with SessionLocal() as db:
            import os
            now = datetime.now(timezone.utc)
            expired = (await db.execute(text(
                "SELECT id, file_path FROM data_exports WHERE expires_at < :now AND status = 'completed'"
            ), {"now": now})).fetchall()
            for exp in expired:
                if exp.file_path and os.path.exists(exp.file_path):
                    os.remove(exp.file_path)
                await db.execute(text(
                    "UPDATE data_exports SET status = 'expired' WHERE id = :id"
                ), {"id": exp.id})
            await db.commit()
            return {"cleaned_exports": len(expired)}
    return _run_async(run())


@celery_app.task(name="src.saas.governance.expire_invites_task")
def expire_invites_task():
    async def run():
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(text(
                "UPDATE org_invites SET status = 'expired' WHERE status = 'pending' AND expires_at < :now"
            ), {"now": now})
            await db.commit()
            return {"expired_invites": result.rowcount or 0}
    return _run_async(run())


@celery_app.task(name="src.saas.governance.apply_scheduled_plan_changes_task")
def apply_scheduled_plan_changes_task():
    async def run():
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            pending = (await db.execute(text(
                "SELECT id, organization_id, target_plan_id, target_plan_version "
                "FROM plan_change_requests "
                "WHERE status = 'scheduled' AND effective_at <= :now"
            ), {"now": now})).fetchall()
            for pcr in pending:
                await db.execute(text(
                    "UPDATE org_subscriptions SET plan_id = :pid, plan_version = :ver, "
                    "updated_at = :now WHERE organization_id = :oid AND status IN ('active','trialing','grace')"
                ), {"pid": pcr.target_plan_id, "ver": pcr.target_plan_version,
                    "now": now, "oid": pcr.organization_id})
                await db.execute(text(
                    "UPDATE plan_change_requests SET status = 'applied' WHERE id = :id"
                ), {"id": pcr.id})
            await db.commit()
            return {"applied_changes": len(pending)}
    return _run_async(run())


@celery_app.task(name="src.saas.governance.verify_audit_log_chain_task")
def verify_audit_log_chain_task():
    async def run():
        async with SessionLocal() as db:
            from src.models.saas import AuditIntegrityCheck
            now = datetime.now(timezone.utc)
            # Check platform audit logs for hash chain integrity
            events = (await db.execute(text("""
                SELECT id, event_hash, previous_event_hash, created_at
                FROM audit_logs WHERE organization_id IS NULL
                ORDER BY created_at
            """))).fetchall()

            status = "passed"
            failed_id = None
            for i in range(1, len(events)):
                curr = events[i]
                prev = events[i - 1]
                if curr.previous_event_hash and curr.previous_event_hash != prev.event_hash:
                    status = "failed"
                    failed_id = curr.id
                    break

            check = AuditIntegrityCheck(
                scope="platform", checked_at=now, status=status,
                failed_at_event_id=failed_id,
                details_json={"events_checked": len(events), "status": status},
            )
            db.add(check)
            await db.commit()
            return {"status": status, "events_checked": len(events)}
    return _run_async(run())


@celery_app.task(name="src.saas.governance.expire_platform_access_sessions_task")
def expire_platform_access_sessions_task():
    async def run():
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(text(
                "UPDATE platform_access_sessions SET status = 'expired' "
                "WHERE status = 'active' AND expires_at < :now"
            ), {"now": now})
            await db.commit()
            return {"expired_sessions": result.rowcount or 0}
    return _run_async(run())


@celery_app.task(name="src.saas.governance.expire_feature_flag_overrides_task")
def expire_feature_flag_overrides_task():
    async def run():
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(text(
                "DELETE FROM feature_flag_overrides WHERE expires_at < :now"
            ), {"now": now})
            await db.commit()
            return {"expired_overrides": result.rowcount or 0}
    return _run_async(run())


@celery_app.task(name="src.saas.governance.expire_emergency_pauses_task")
def expire_emergency_pauses_task():
    async def run():
        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(text(
                "UPDATE emergency_pauses SET status = 'expired' "
                "WHERE status = 'active' AND expires_at IS NOT NULL AND expires_at < :now"
            ), {"now": now})
            await db.commit()
            return {"expired_pauses": result.rowcount or 0}
    return _run_async(run())
