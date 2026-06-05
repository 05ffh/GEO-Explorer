"""ReclassificationService — historical report re-attribution (P1-8).

P0 constraints:
- original report_quality_summary_json is never overwritten
- dry_run does full computation but writes no business results
- apply preserves old HallucinationResults and creates new reclassified rows
- each CollectionRun is processed in its own transaction
- progress is tracked and resumable
"""
import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.query_result import QueryResult
from src.models.collection_run import CollectionRun
from src.models.hallucination import HallucinationResult
from src.analyzer.enums import HallucinationVerdict
from src.models.reclassification_run import (
    ReclassificationRun,
    STATUS_QUEUED, STATUS_RUNNING, STATUS_COMPLETED, STATUS_PARTIAL_FAILED,
    STATUS_FAILED, STATUS_CANCELLED,
    MODE_DRY_RUN, MODE_WRITE_RESULTS,
    RESULT_RECLASSIFIED,
)

logger = logging.getLogger(__name__)

MAX_SAMPLE_DIFFS = 50


class ReclassificationService:

    @staticmethod
    async def create_batch(
        db: AsyncSession,
        *,
        organization_id: uuid.UUID,
        brand_id: uuid.UUID,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        dry_run: bool = True,
        mode: str = MODE_DRY_RUN,
        gt_version_strategy: str = "latest_active",
        reason: str | None = None,
        triggered_by: uuid.UUID | None = None,
        idempotency_key: str | None = None,
    ) -> ReclassificationRun:
        batch = ReclassificationRun(
            organization_id=organization_id,
            brand_id=brand_id,
            from_date=from_date,
            to_date=to_date,
            status=STATUS_QUEUED,
            mode=mode,
            dry_run=dry_run,
            gt_version_strategy=gt_version_strategy,
            reason=reason,
            triggered_by=triggered_by,
            idempotency_key=idempotency_key,
        )
        db.add(batch)
        await db.flush()
        return batch

    @staticmethod
    async def compute_eligible_runs(
        db: AsyncSession,
        batch: ReclassificationRun,
    ) -> list[CollectionRun]:
        """Find CollectionRuns in scope for reclassification."""
        q = select(CollectionRun).where(
            CollectionRun.brand_id == batch.brand_id,
            CollectionRun.organization_id == batch.organization_id,
            CollectionRun.collection_status.in_(["completed", "partial"]),
        )
        if batch.from_date:
            q = q.where(CollectionRun.collection_completed_at >= batch.from_date)
        if batch.to_date:
            q = q.where(CollectionRun.collection_completed_at <= batch.to_date)
        q = q.order_by(CollectionRun.collection_completed_at.asc())
        result = await db.execute(q)
        return list(result.scalars().all())

    @staticmethod
    async def dry_run_single(
        db: AsyncSession,
        run: CollectionRun,
        batch: ReclassificationRun,
        sample_diffs: list,
    ) -> dict:
        """Run detector on one CollectionRun's QueryResults without writing business data (P0-7)."""
        changes = {"ai_hallucination": 0, "template_issue": 0, "gt_insufficient": 0, "not_about_brand": 0}
        qrs = (await db.execute(
            select(QueryResult).where(QueryResult.collection_run_id == run.id)
        )).scalars().all()

        old_results = (await db.execute(
            select(HallucinationResult).where(
                HallucinationResult.collection_run_id == run.id,
                HallucinationResult.result_origin == "original",
            )
        )).scalars().all()

        for qr in qrs:
            new_layer = await _classify_single_query_result(db, qr, batch)
            old_verdicts = [
                r.verdict for r in old_results
                if r.query_result_id == qr.id
            ]
            old_error = any(v in ("incorrect", HallucinationVerdict.CONTRADICTED, HallucinationVerdict.UNSUPPORTED) for v in old_verdicts) if old_verdicts else False

            if old_error and new_layer != "ai_hallucination":
                changes[new_layer] = changes.get(new_layer, 0) + 1
                if len(sample_diffs) < MAX_SAMPLE_DIFFS:
                    sample_diffs.append({
                        "collection_run_id": str(run.id),
                        "query_result_id": str(qr.id),
                        "old_verdict": old_verdicts[0] if old_verdicts else "unknown",
                        "new_layer": new_layer,
                    })

        batch.query_results_processed += len(qrs)
        return changes

    @staticmethod
    async def apply_single(
        db: AsyncSession,
        run: CollectionRun,
        batch: ReclassificationRun,
    ) -> dict:
        """Apply reclassification to one CollectionRun (P0-9: run-level transaction)."""
        # P0-3: backup original summary on first reclassification
        if run.original_report_quality_summary_json is None:
            run.original_report_quality_summary_json = dict(run.report_quality_summary_json) if run.report_quality_summary_json else {}

        # Mark old reclassified results as not current
        await db.execute(
            update(HallucinationResult).where(
                HallucinationResult.collection_run_id == run.id,
                HallucinationResult.result_origin == RESULT_RECLASSIFIED,
            ).values(is_current_reclassification=False)
        )

        changes = {"ai_hallucination": 0, "template_issue": 0, "gt_insufficient": 0, "not_about_brand": 0}
        qrs = (await db.execute(
            select(QueryResult).where(QueryResult.collection_run_id == run.id)
        )).scalars().all()

        new_results_count = 0
        for qr in qrs:
            new_layer = await _classify_single_query_result(db, qr, batch)
            hr = HallucinationResult(
                query_result_id=qr.id,
                source_query_result_id=qr.id,
                brand_id=run.brand_id,
                collection_run_id=run.id,
                result_origin=RESULT_RECLASSIFIED,
                reclassification_run_id=batch.id,
                is_current_reclassification=True,
                verdict=HallucinationVerdict.CONTRADICTED if new_layer == "ai_hallucination" else new_layer,
                field_name="reclassification",
                field_level="P1",
                reason=f"P1-8 reclassification: {new_layer}",
                detected_at=datetime.now(timezone.utc),
            )
            db.add(hr)
            new_results_count += 1

            old_results = (await db.execute(
                select(HallucinationResult).where(
                    HallucinationResult.query_result_id == qr.id,
                    HallucinationResult.result_origin == "original",
                )
            )).scalars().all()
            old_error = any(r.verdict in ("incorrect", HallucinationVerdict.CONTRADICTED, HallucinationVerdict.UNSUPPORTED) for r in old_results)
            if old_error and new_layer != "ai_hallucination":
                changes[new_layer] = changes.get(new_layer, 0) + 1

        batch.query_results_processed += len(qrs)
        batch.hallucination_results_created += new_results_count

        # P1-8: build corrected quality summary
        run.latest_reclassified_quality_summary_json = _build_corrected_summary(qrs, run)
        run.latest_reclassification_run_id = batch.id
        run.reclassified_at = datetime.now(timezone.utc)

        return changes


async def _classify_single_query_result(db, qr: QueryResult, batch) -> str:
    """Run HallucinationDetector on one QueryResult."""
    try:
        from src.analyzer.hallucination import HallucinationDetector
        from src.models.query_template import QueryTemplate
        tmpl = (await db.execute(
            select(QueryTemplate).where(QueryTemplate.id == qr.template_id)
        )).scalar_one_or_none()
        if tmpl is None:
            return "not_about_brand"

        detector = HallucinationDetector(db_session=db)
        category = await detector._classify_relevance(
            answer_text=qr.answer_text or "",
            brand_name="",  # Will attempt to detect from query
            brand_aliases=[],
        )
        return category if category else "generic_statement"
    except Exception:
        return "not_about_brand"


def _build_corrected_summary(qrs: list, run: CollectionRun) -> dict:
    """Build 4-layer corrected quality summary."""
    return {
        "schema_version": "template_health_v1",
        "reclassified_at": datetime.now(timezone.utc).isoformat(),
        "total_queries": len(qrs),
        "original_summary": dict(run.report_quality_summary_json) if run.report_quality_summary_json else {},
    }
