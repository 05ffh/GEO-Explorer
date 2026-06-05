import logging
import traceback
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

logger = logging.getLogger(__name__)


def should_analyze(run, success_platform_count: int, min_platforms: int = 2, min_queries: int = 10) -> bool:
    return (
        run.collection_status in ("completed", "partial")
        and success_platform_count >= min_platforms
        and run.success_count >= min_queries
    )


async def run_analysis_for_collection(
    collection_run_id: UUID,
    org_id: UUID,
    db: AsyncSession,
) -> None:
    from src.models.collection_run import CollectionRun
    from src.models.query_result import QueryResult
    from src.models.metrics_snapshot import MetricsSnapshot
    from src.config import settings
    from src.analyzer.pipeline import compute_and_save_metrics

    run_obj = (await db.execute(
        select(CollectionRun).where(CollectionRun.id == collection_run_id)
    )).scalar_one_or_none()
    if not run_obj:
        logger.error("CollectionRun %s not found", collection_run_id)
        return

    # 幂等性：已有 MetricsSnapshot 则跳过
    existing = (await db.execute(
        select(func.count(MetricsSnapshot.id)).where(
            MetricsSnapshot.collection_run_id == collection_run_id,
        )
    )).scalar()
    if existing and existing > 0:
        logger.info("MetricsSnapshot already exists for %s, skipping analysis", collection_run_id)
        return

    # 计算成功平台数
    platforms = (await db.execute(
        select(func.count(func.distinct(QueryResult.platform))).where(
            QueryResult.collection_run_id == collection_run_id,
            QueryResult.status == "success",
        )
    )).scalar()

    if not should_analyze(
        run_obj, success_platform_count=platforms,
        min_platforms=settings.min_success_platforms_for_analysis,
        min_queries=settings.min_success_queries_for_analysis,
    ):
        run_obj.analysis_status = "skipped"
        run_obj.analysis_error_message = (
            f"Insufficient data: {platforms} platforms, {run_obj.success_count} queries"
        )
        await db.commit()
        return

    run_obj.analysis_status = "running"
    run_obj.analysis_started_at = datetime.now(timezone.utc)
    await db.commit()

    try:
        await compute_and_save_metrics(
            str(run_obj.brand_id), str(org_id), str(collection_run_id), db,
        )
        run_obj.analysis_status = "completed"
    except Exception as e:
        run_obj.analysis_status = "failed"
        run_obj.analysis_error_message = str(e)
        run_obj.analysis_error_trace = traceback.format_exc()
        logger.exception(
            "Analysis failed",
            extra={
                "collection_run_id": str(collection_run_id),
                "brand_id": str(run_obj.brand_id),
                "organization_id": str(org_id),
            },
        )
    finally:
        run_obj.analysis_completed_at = datetime.now(timezone.utc)
        await db.commit()
