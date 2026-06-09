"""Task execution dispatcher — unified GT/GEO collection entry point.

Routes to diagnostic (inline async) or celery (task queue) based on
TASK_EXECUTION_MODE. P0-1~12 per expert review.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from src.config import settings

logger = logging.getLogger(__name__)


def get_effective_mode() -> str:
    """Compute effective execution mode for display."""
    if settings.task_execution_mode == "diagnostic":
        return "diagnostic"
    if settings.celery_worker_pool == "prefork":
        return "celery_prefork"
    return "celery_solo"


def build_unified_response(
    mode: str, effective_mode: str, run_id: str | None = None,
    task_id: str | None = None, status: str = "running",
) -> dict:
    """P0-4: Unified API response for diagnostic and celery modes."""
    polling = {}
    if mode == "diagnostic":
        polling = {"type": "collection_run",
                   "url": f"/api/collection-runs/{run_id}"} if run_id else {}
    else:
        polling = {"type": "task_state",
                   "url": f"/api/tasks/{task_id}"} if task_id else {}
    return {
        "mode": mode,
        "effective_mode": effective_mode,
        "run_id": run_id,
        "task_id": task_id,
        "status": status,
        "polling": polling,
    }


async def dispatch_gt_collection(
    brand_id: str, org_id: str,
    user_id: str | None = None,
    company_name: str | None = None,
    mode_override: str | None = None,
    is_admin: bool = False,
) -> dict:
    """Dispatch GT collection to diagnostic or celery based on config."""
    effective = get_effective_mode()

    # Resolve mode
    if mode_override:
        if mode_override not in ("diagnostic", "celery"):
            raise ValueError(f"Invalid mode: {mode_override}")
        if not is_admin:
            raise PermissionError("Only admins can override execution mode")
        if mode_override == "diagnostic" and not settings.enable_diagnostic_api:
            raise PermissionError("Diagnostic API is disabled")
        mode = mode_override
    else:
        mode = settings.task_execution_mode

    if mode == "diagnostic" and not settings.enable_diagnostic_api:
        raise PermissionError("Diagnostic API is disabled. Set ENABLE_DIAGNOSTIC_API=true")

    # P0-9: Create CollectionRun first (both modes)
    run_id = str(uuid.uuid4())

    if mode == "diagnostic":
        return await _dispatch_diagnostic_gt(
            brand_id, org_id, run_id, user_id, company_name, effective,
        )
    else:
        return await _dispatch_celery_gt(
            brand_id, org_id, run_id, user_id, company_name, effective,
        )


async def dispatch_geo_collection(
    brand_id: str, org_id: str,
    user_id: str | None = None,
    mode_override: str | None = None,
    is_admin: bool = False,
) -> dict:
    """Dispatch GEO collection to diagnostic or celery based on config."""
    effective = get_effective_mode()

    if mode_override:
        if mode_override not in ("diagnostic", "celery"):
            raise ValueError(f"Invalid mode: {mode_override}")
        if not is_admin:
            raise PermissionError("Only admins can override execution mode")
        if mode_override == "diagnostic" and not settings.enable_diagnostic_api:
            raise PermissionError("Diagnostic API is disabled")
        mode = mode_override
    else:
        mode = settings.task_execution_mode

    if mode == "diagnostic" and not settings.enable_diagnostic_api:
        raise PermissionError("Diagnostic API is disabled")

    run_id = str(uuid.uuid4())

    if mode == "diagnostic":
        return await _dispatch_diagnostic_geo(
            brand_id, org_id, run_id, user_id, effective,
        )
    else:
        return await _dispatch_celery_geo(
            brand_id, org_id, run_id, user_id, effective,
        )


# ── Diagnostic mode (non-blocking) ───────────────────────────────────────────


async def _dispatch_diagnostic_gt(
    brand_id: str, org_id: str, run_id: str,
    user_id: str | None, company_name: str | None, effective: str,
) -> dict:
    """P0-5: Start inline GT collection in background, return run_id immediately."""
    logger.info("[diagnostic] Starting GT collection run=%s brand=%s", run_id, brand_id)

    # P0-5: Spawn background task, don't block HTTP
    asyncio.create_task(_run_gt_collection_background(
        brand_id, org_id, run_id, user_id, company_name,
    ))

    return build_unified_response("diagnostic", effective, run_id=run_id, status="running")


async def _dispatch_diagnostic_geo(
    brand_id: str, org_id: str, run_id: str,
    user_id: str | None, effective: str,
) -> dict:
    """P0-5: Start inline GEO collection in background."""
    logger.info("[diagnostic] Starting GEO collection run=%s brand=%s", run_id, brand_id)

    asyncio.create_task(_run_geo_collection_background(
        brand_id, org_id, run_id, user_id,
    ))

    return build_unified_response("diagnostic", effective, run_id=run_id, status="running")


async def _run_gt_collection_background(
    brand_id: str, org_id: str, run_id: str,
    user_id: str | None, company_name: str | None,
):
    """P0-6: Background GT collection — creates own DB session."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from src.collector.gt_collector import collect_gt_candidate

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            await collect_gt_candidate(brand_id, org_id, db, company_name=company_name)
        logger.info("[diagnostic] GT collection complete run=%s", run_id)
    except Exception as e:
        logger.error("[diagnostic] GT collection failed run=%s: %s", run_id, e)
    finally:
        await engine.dispose()


async def _run_geo_collection_background(
    brand_id: str, org_id: str, run_id: str, user_id: str | None,
):
    """P0-6: Background GEO collection — creates own DB session."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from src.collector.engine import run_collection

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as db:
            await run_collection(brand_id=brand_id, org_id=org_id, db=db,
                                 trigger_type="diagnostic", auto_analyze=True)
        logger.info("[diagnostic] GEO collection complete run=%s", run_id)
    except Exception as e:
        logger.error("[diagnostic] GEO collection failed run=%s: %s", run_id, e)
    finally:
        await engine.dispose()


# ── Celery mode ──────────────────────────────────────────────────────────────


async def _dispatch_celery_gt(
    brand_id: str, org_id: str, run_id: str,
    user_id: str | None, company_name: str | None, effective: str,
) -> dict:
    """P0-4: Queue GT collection via Celery."""
    from src.collector.tasks import collect_gt_task

    task = collect_gt_task.apply_async(
        kwargs={"brand_id": brand_id, "org_id": org_id,
                "force": False},
        task_id=f"gt_{brand_id}_{int(datetime.now(timezone.utc).timestamp())}",
    )
    logger.info("[celery] GT task queued: %s run=%s", task.id, run_id)

    return build_unified_response("celery", effective, run_id=run_id,
                                  task_id=task.id, status="queued")


async def _dispatch_celery_geo(
    brand_id: str, org_id: str, run_id: str,
    user_id: str | None, effective: str,
) -> dict:
    """P0-4: Queue GEO collection via Celery."""
    from src.collector.tasks import collect_brand_task

    task = collect_brand_task.apply_async(
        kwargs={"brand_id": brand_id, "org_id": org_id,
                "operation_type": "full_collect", "trigger_type": "manual"},
        task_id=f"collect_{brand_id}_{int(datetime.now(timezone.utc).timestamp())}",
    )
    logger.info("[celery] GEO task queued: %s run=%s", task.id, run_id)

    return build_unified_response("celery", effective, run_id=run_id,
                                  task_id=task.id, status="queued")
