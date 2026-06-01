"""Benchmark computation Celery tasks (P2-1)."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.celery_app import app
from src.config import settings
from src.benchmark.engine import compute_industry_benchmark, get_active_definition

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

ALL_INDUSTRIES = [
    "finance", "fnb", "saas_b2b", "ev_mobility", "consumer_electronics",
    "healthcare_pharma", "education", "ecommerce_retail", "travel_hospitality",
    "real_estate_home", "industrial_b2b", "logistics_crossborder",
    "ai_cloud_devtools", "beauty_fashion", "public_sector_city",
]


@app.task(bind=True, max_retries=1, acks_late=True, soft_time_limit=300, time_limit=600)
def compute_all_benchmarks(self):
    """Compute benchmark snapshots for all industries. Beat: daily at 2am."""
    async def _run():
        async with SessionLocal() as db:
            definition = await get_active_definition(db)
            results = {}
            for industry_key in ALL_INDUSTRIES:
                try:
                    snapshot = await compute_industry_benchmark(
                        industry_key=industry_key, db=db, definition=definition,
                    )
                    results[industry_key] = {
                        "snapshot_id": str(snapshot.id),
                        "status": snapshot.status,
                        "quality_level": snapshot.quality_level,
                        "sample_count": snapshot.sample_brand_count,
                    }
                except Exception as exc:
                    logger.error(f"Benchmark failed for {industry_key}: {exc}")
                    results[industry_key] = {"status": "failed", "error": str(exc)[:200]}
            return {"status": "completed", "results": results}

    return asyncio.run(_run())


@app.task(bind=True, max_retries=1, acks_late=True, soft_time_limit=300, time_limit=600)
def compute_org_benchmarks(self, org_id: str):
    """Compute benchmarks for a specific organization."""
    async def _run():
        import uuid
        async with SessionLocal() as db:
            definition = await get_active_definition(db)
            results = {}
            for industry_key in ALL_INDUSTRIES:
                try:
                    snapshot = await compute_industry_benchmark(
                        industry_key=industry_key, db=db,
                        definition=definition, org_id=uuid.UUID(org_id),
                    )
                    results[industry_key] = {"status": snapshot.status}
                except Exception as exc:
                    logger.error(f"Org benchmark failed for {industry_key}: {exc}")
                    results[industry_key] = {"status": "failed", "error": str(exc)[:200]}
            return {"status": "completed", "org_id": org_id, "results": results}
    return asyncio.run(_run())


@app.task(bind=True, max_retries=1, acks_late=True, soft_time_limit=120, time_limit=300)
def check_benchmark_freshness(self):
    """Mark stale/expired benchmarks. Beat: every 4 hours."""
    async def _run():
        from sqlalchemy import text, update
        from src.models.benchmark_snapshot import BenchmarkSnapshot

        async with SessionLocal() as db:
            now = datetime.now(timezone.utc)
            await db.execute(
                text("UPDATE benchmark_snapshots SET freshness_status='expired' "
                     "WHERE freshness_status NOT IN ('expired','superseded') AND valid_until < :now"),
                {"now": now},
            )
            await db.execute(
                text("UPDATE benchmark_snapshots SET freshness_status='stale' "
                     "WHERE freshness_status='fresh' AND valid_until < :soon"),
                {"soon": now},
            )
            await db.commit()
            return {"status": "completed"}

    return asyncio.run(_run())
