"""P1-8: Celery task for async reclassification execution (P0-2, P0-9)."""
import logging
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.celery_app import celery_app
from src.database import async_session_factory
from src.models.collection_run import CollectionRun
from src.models.reclassification_run import (
    ReclassificationRun,
    STATUS_RUNNING, STATUS_COMPLETED, STATUS_PARTIAL_FAILED, STATUS_CANCELLED,
)
from src.services.reclassification_service import ReclassificationService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="reclassification.run")
def run_reclassification(self, batch_id: str):
    """Execute reclassification batch asynchronously."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(_execute(batch_id))


async def _execute(batch_id: str):
    service = ReclassificationService()

    # Load batch
    async with async_session_factory() as db:
        async with db.begin():
            batch_result = await db.execute(
                select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
            )
            batch = batch_result.scalar_one_or_none()
            if batch is None or batch.status == STATUS_CANCELLED:
                return

            batch.status = STATUS_RUNNING
            batch.started_at = datetime.now(timezone.utc)
            runs = await service.compute_eligible_runs(db, batch)
            batch.eligible_runs_count = len(runs)

        sample_diffs = []
        total_changes = {"ai_hallucination": 0, "template_issue": 0, "gt_insufficient": 0, "not_about_brand": 0}

        for run in runs:
            # Check cancellation
            async with async_session_factory() as check_db:
                current = (await check_db.execute(
                    select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
                )).scalar_one()
                if current.status == STATUS_CANCELLED:
                    return

            try:
                async with async_session_factory() as run_db:
                    async with run_db.begin():
                        local_batch = (await run_db.execute(
                            select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
                        )).scalar_one()
                        local_run = (await run_db.execute(
                            select(CollectionRun).where(CollectionRun.id == run.id)
                        )).scalar_one()

                        if local_batch.dry_run:
                            changes = await service.dry_run_single(run_db, local_run, local_batch, sample_diffs)
                        else:
                            changes = await service.apply_single(run_db, local_run, local_batch)

                        local_batch.runs_processed += 1
                        for k, v in changes.items():
                            total_changes[k] = total_changes.get(k, 0) + v
                        local_batch.progress_json = {
                            "total_runs": local_batch.eligible_runs_count,
                            "completed_runs": local_batch.runs_processed,
                            "failed_runs": local_batch.runs_failed,
                            "current_run_id": str(run.id),
                            "query_results_processed": local_batch.query_results_processed,
                        }
            except Exception as e:
                async with async_session_factory() as err_db:
                    async with err_db.begin():
                        err_batch = (await err_db.execute(
                            select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
                        )).scalar_one()
                        err_batch.runs_failed += 1
                        err_summary = dict(err_batch.error_summary_json)
                        err_summary[str(run.id)] = str(e)
                        err_batch.error_summary_json = err_summary

        # Finalize
        async with async_session_factory() as final_db:
            async with final_db.begin():
                final_batch = (await final_db.execute(
                    select(ReclassificationRun).where(ReclassificationRun.id == batch_id)
                )).scalar_one()
                final_batch.classification_changes_json = total_changes
                if sample_diffs:
                    final_batch.sample_diffs_json = sample_diffs[:50]
                final_batch.completed_at = datetime.now(timezone.utc)
                if final_batch.runs_failed > 0:
                    final_batch.status = STATUS_PARTIAL_FAILED
                else:
                    final_batch.status = STATUS_COMPLETED
                if not final_batch.dry_run:
                    final_batch.is_current_for_range = True
                    await final_db.execute(
                        update(ReclassificationRun).where(
                            ReclassificationRun.brand_id == final_batch.brand_id,
                            ReclassificationRun.id != final_batch.id,
                            ReclassificationRun.is_current_for_range.is_(True),
                        ).values(is_current_for_range=False)
                    )
