"""DataDeletion async Celery task — idempotent, batched, checkpointed deletion (P0-3/P0-4/P0-5).

Celery tasks are defined at module level (standard pattern). Core logic functions
(_batch_delete, _collect_file_keys, _delete_files) are at module level for testability.
"""
import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

BATCH_SIZE = 500

# FK-aware deletion order: child tables first, parent tables last
DELETE_ORDER = [
    "content_packages", "content_library",
    "report_delivery_attempts", "report_download_events", "report_download_links",
    "report_artifacts", "report_schedule_runs", "report_subscriptions",
    "report_schedules", "report_batches", "report_brandings",
    "publish_status_callbacks", "publish_events", "publish_attempts",
    "publish_requests", "publish_batches", "cms_field_mappings", "publish_targets",
    "hallucination_results",
    "insight_summaries", "action_themes", "action_plans",
    "gt_reviews", "gt_evidences", "gt_candidates", "ground_truth_versions",
    "metrics_snapshots", "gap_attribution_results",
    "benchmark_snapshots", "benchmark_definitions",
    "trend_insight_events", "trend_insights", "platform_trend_incidents",
    "trend_analysis_definitions", "model_events", "impact_events",
    "query_results", "collection_runs", "competitor_sets",
    "query_templates", "prompt_versions",
    "api_usage_logs", "api_key_usage_logs", "api_keys",
    "data_exports",
]

CASCADE_ORG_TABLES = [
    "org_invites", "org_subscriptions", "usage_events", "usage_snapshots",
    "cost_alerts", "queue_alerts", "task_events", "task_states",
    "audit_integrity_checks", "rate_limit_policies",
]


# ── Core logic (no Celery dependency) ────────────────────────────────────────

async def process_deletion(db, deletion_request_id: str, celery_task_id: str = "") -> dict:
    eid = uuid.UUID(deletion_request_id)
    dr = (await db.execute(text(
        "SELECT * FROM data_deletion_requests WHERE id = :id FOR UPDATE"
    ), {"id": eid})).fetchone()
    if not dr:
        return {"status": "error", "detail": "Deletion request not found"}

    status = dr.status
    if status in ("completed", "completed_with_warnings"):
        return {"status": "noop", "detail": "Already completed"}
    if status == "processing":
        return {"status": "noop", "detail": "Already processing"}
    if status not in ("approved", "failed"):
        return {"status": "noop", "detail": f"Status {status} not eligible"}

    org_id = dr.organization_id
    brand_id = dr.brand_id
    scope = dr.scope
    started_at = datetime.now(timezone.utc)
    last_processed_id = dr.last_processed_id

    await db.execute(text(
        "UPDATE data_deletion_requests SET status = 'processing', "
        "retry_count = retry_count + 1, task_state_id = :tid WHERE id = :id"
    ), {"tid": celery_task_id, "id": eid})
    await db.commit()

    deleted_counts = {}
    failed_table = None
    failed_reason = None

    try:
        file_keys = await _collect_file_keys(db, org_id, brand_id, scope)

        for table_name in DELETE_ORDER:
            try:
                count = await _batch_delete(db, table_name, org_id, brand_id, scope,
                                            last_processed_id, BATCH_SIZE)
                deleted_counts[table_name] = count
                if count > 0:
                    last_processed_id = None
            except Exception as exc:
                logger.error(f"Deletion failed at table {table_name}: {exc}")
                failed_table = table_name
                failed_reason = str(exc)[:500]
                await db.execute(text(
                    "UPDATE data_deletion_requests SET failed_table = :ft, "
                    "failed_reason = :fr, last_processed_id = :lp WHERE id = :id"
                ), {"ft": failed_table, "fr": failed_reason, "lp": last_processed_id, "id": eid})
                await db.commit()
                raise

        if scope == "brand" and brand_id:
            try:
                await db.execute(text("DELETE FROM brands WHERE id = :bid"), {"bid": brand_id})
                deleted_counts["brands"] = 1
            except Exception as exc:
                failed_table = "brands"
                failed_reason = str(exc)[:500]
                raise

        if scope == "organization":
            for table_name in CASCADE_ORG_TABLES:
                try:
                    count = await _batch_delete(db, table_name, org_id, None, scope, None, BATCH_SIZE)
                    deleted_counts[table_name] = count
                except Exception:
                    logger.warning(f"Could not delete from {table_name}, continuing")
            await db.execute(text("DELETE FROM users WHERE organization_id = :oid"), {"oid": org_id})
            await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": org_id})
            deleted_counts["organizations"] = 1

        file_deleted, file_failed, failed_assets = await _delete_files(file_keys)

        receipt_data = {
            "request_id": str(eid), "organization_id": str(org_id),
            "scope": scope, "brand_id": str(brand_id) if brand_id else None,
            "requested_by": str(dr.requested_by) if dr.requested_by else None,
            "approved_by": str(dr.approved_by) if dr.approved_by else None,
            "deleted_counts": deleted_counts, "anonymized_counts": {},
            "retained_items": [{"type": "security_audit", "reason": "retained for 180 days"}],
            "file_deleted_count": file_deleted, "file_failed_count": file_failed,
            "completed_at": started_at.isoformat(),
        }
        canonical = json.dumps(receipt_data, sort_keys=True, ensure_ascii=False)
        receipt_hash = hashlib.sha256(canonical.encode()).hexdigest()

        from src.models.saas import DeletionReceipt
        receipt = DeletionReceipt(
            deletion_request_id=eid, organization_id=org_id,
            scope=scope, brand_id=brand_id,
            requested_by=dr.requested_by, approved_by=dr.approved_by,
            started_at=started_at, completed_at=started_at,
            affected_tables_json=list(deleted_counts.keys()),
            deleted_counts_json=deleted_counts,
            retained_items_json=receipt_data["retained_items"],
            file_deleted_count=file_deleted, file_failed_count=file_failed,
            failed_assets_json=failed_assets, receipt_hash=receipt_hash,
        )
        db.add(receipt)

        overall_status = "completed_with_warnings" if file_failed > 0 else "completed"
        await db.execute(text(
            "UPDATE data_deletion_requests SET status = :st, completed_at = :now, "
            "failed_table = NULL, failed_reason = NULL WHERE id = :id"
        ), {"st": overall_status, "now": datetime.now(timezone.utc), "id": eid})
        await db.commit()

        return {"status": overall_status, "deletion_request_id": deletion_request_id,
                "deleted_counts": deleted_counts, "file_deleted_count": file_deleted,
                "file_failed_count": file_failed, "receipt_hash": receipt_hash}

    except Exception as exc:
        new_status = "manual_review" if (dr.retry_count or 0) >= 2 else "failed"
        await db.execute(text(
            "UPDATE data_deletion_requests SET status = :st, failed_table = :ft, "
            "failed_reason = :fr, last_processed_id = :lp WHERE id = :id"
        ), {"st": new_status, "ft": failed_table, "fr": failed_reason or str(exc)[:500],
            "lp": last_processed_id, "id": eid})
        await db.commit()
        raise


async def _batch_delete(db, table_name: str, org_id, brand_id, scope: str,
                        last_processed_id: str | None, batch_size: int) -> int:
    total_deleted = 0
    while True:
        exists = (await db.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :t)"
        ), {"t": table_name})).scalar()
        if not exists:
            return 0

        conditions = []
        params = {}
        if scope == "brand" and brand_id:
            cols = (await db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND column_name IN ('brand_id', 'organization_id') "
                "ORDER BY column_name DESC"
            ), {"t": table_name})).fetchall()
            for col in cols:
                cn = col.column_name
                if cn == "brand_id" and brand_id:
                    conditions.append(f"{cn} = :bid")
                    params["bid"] = brand_id
                elif cn == "organization_id" and not conditions:
                    conditions.append(f"{cn} = :oid")
                    params["oid"] = org_id
        elif scope == "organization" and org_id:
            conditions.append("organization_id = :oid")
            params["oid"] = org_id

        if not conditions:
            break

        if last_processed_id:
            conditions.append("id > :lp::uuid")
            params["lp"] = last_processed_id

        params["limit"] = batch_size
        result = await db.execute(text(
            f"DELETE FROM {table_name} WHERE {' AND '.join(conditions)} "
            f"ORDER BY id LIMIT :limit RETURNING id"
        ), params)
        batch_ids = result.fetchall()
        batch_count = len(batch_ids)
        total_deleted += batch_count
        if batch_ids:
            last_processed_id = str(batch_ids[-1].id)
        await db.commit()
        if batch_count < batch_size:
            break
    return total_deleted


async def _collect_file_keys(db, org_id, brand_id, scope: str) -> list[str]:
    paths = []
    exports = (await db.execute(text(
        "SELECT file_path FROM data_exports WHERE organization_id = :oid AND file_path IS NOT NULL"
    ), {"oid": org_id})).fetchall()
    for row in exports:
        if row.file_path and os.path.exists(row.file_path):
            paths.append(row.file_path)
    reports = (await db.execute(text(
        "SELECT file_path FROM report_artifacts WHERE organization_id = :oid AND file_path IS NOT NULL"
    ), {"oid": org_id})).fetchall()
    for row in reports:
        if row.file_path and os.path.exists(row.file_path):
            paths.append(row.file_path)
    return paths


async def _delete_files(paths: list[str]) -> tuple[int, int, list]:
    deleted, failed, failed_assets = 0, 0, []
    for path in paths:
        try:
            os.remove(path)
            deleted += 1
        except FileNotFoundError:
            deleted += 1
        except Exception as exc:
            failed += 1
            failed_assets.append({"path": path, "error": str(exc)[:200], "retryable": True})
    return deleted, failed, failed_assets


# ── Celery tasks ─────────────────────────────────────────────────────────────

def _get_celery():
    from src.celery_app import app
    return app


data_deletion_task = None
data_deletion_scan_task = None
data_deletion_retry_scan_task = None


def _register_celery_tasks():
    global data_deletion_task, data_deletion_scan_task, data_deletion_retry_scan_task
    app = _get_celery()

    @app.task(bind=True, max_retries=2, soft_time_limit=600, time_limit=900)
    def _deletion_task(self, deletion_request_id: str):
        async def run():
            async with SessionLocal() as db:
                return await process_deletion(db, deletion_request_id, self.request.id or "")
        return asyncio.run(run())

    @app.task(bind=True, max_retries=1, soft_time_limit=120, time_limit=180)
    def _scan_task(self):
        async def scan():
            async with SessionLocal() as db:
                rows = (await db.execute(text(
                    "SELECT id FROM data_deletion_requests "
                    "WHERE status = 'approved' AND scheduled_delete_at <= :now "
                    "ORDER BY created_at LIMIT 10"
                ), {"now": datetime.now(timezone.utc)})).fetchall()
                for row in rows:
                    _deletion_task.delay(str(row.id))
                return {"status": "scanned", "dispatched": len(rows)}
        return asyncio.run(scan())

    @app.task(bind=True, max_retries=1, soft_time_limit=120, time_limit=180)
    def _retry_scan_task(self):
        async def scan():
            async with SessionLocal() as db:
                result = await db.execute(text(
                    "SELECT id FROM data_deletion_requests "
                    "WHERE status = 'failed' AND retry_count < 2 "
                    "ORDER BY created_at LIMIT 10"
                ))
                rows = result.fetchall()
                for row in rows:
                    _deletion_task.delay(str(row.id))
                return {"status": "scanned", "dispatched": len(rows)}
        return asyncio.run(scan())

    data_deletion_task = _deletion_task
    data_deletion_scan_task = _scan_task
    data_deletion_retry_scan_task = _retry_scan_task


# Register tasks when this module is loaded in a Celery worker
try:
    _register_celery_tasks()
except Exception:
    logger.debug("Celery not available — tasks will not be registered (tests/non-worker)")
