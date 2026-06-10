#!/usr/bin/env python3
"""GEO Explorer — Diagnostic collection script (NOT production backend).

Usage: .venv/bin/python scripts/run_collection_diagnostic.py <brand_id> [org_id]

Runs GT + GEO collection inline (single async process, no Celery).
Used for: API key verification, platform connectivity, collection logic debugging.
"""
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger("diagnostic")


async def run_gt_collection(brand_id: str, org_id: str, company: str = ""):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from src.config import settings
    from src.collector.gt_collector import collect_gt_candidate

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        t0 = time.time()
        logger.info("Starting GT collection for brand=%s company=%s", brand_id, company)
        candidate = await collect_gt_candidate(brand_id, org_id, db, company_name=company)
        elapsed = time.time() - t0
        logger.info("GT collection complete: %s, confidence=%s, fields=%d, time=%.0fs",
                     candidate.id, candidate.overall_confidence,
                     len(candidate.candidate_json or {}), elapsed)
    await engine.dispose()
    return candidate


async def run_geo_collection(brand_id: str, org_id: str):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from src.config import settings
    from src.collector.engine import run_collection

    engine = create_async_engine(settings.database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        t0 = time.time()
        logger.info("Starting GEO collection for brand=%s", brand_id)
        run = await run_collection(brand_id=brand_id, org_id=org_id, db=db,
                                   trigger_type="diagnostic", auto_analyze=False)
        elapsed = time.time() - t0
        logger.info("GEO collection: status=%s success=%d/%d time=%.0fs",
                     run.collection_status, run.success_count, run.total_queries, elapsed)
        ps = run.platform_status_json or {}
        for p, s in ps.get("platforms", {}).items():
            logger.info("  %s: success=%d failed=%d rate_limited=%d",
                         p, s["success"], s["failed"], s.get("rate_limited", 0))
    await engine.dispose()
    return run


async def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_collection_diagnostic.py <brand_id> [org_id]")
        sys.exit(1)

    brand_id = sys.argv[1]
    org_id = sys.argv[2] if len(sys.argv) > 2 else "76047f71-11e7-414d-a72f-9b243f6c573f"

    logger.info("=== Diagnostic Mode ===")
    logger.info("Brand: %s  Org: %s", brand_id, org_id)
    logger.info("This runs inline without Celery — for verification only.")

    # GT collection
    gt = await run_gt_collection(brand_id, org_id, company="星巴克")
    # GEO collection
    geo = await run_geo_collection(brand_id, org_id)

    logger.info("=== Diagnostic Complete ===")
    logger.info("GT: %s (confidence=%s)", gt.id, gt.overall_confidence)
    logger.info("GEO: status=%s %d/%d", geo.collection_status, geo.success_count, geo.total_queries)


if __name__ == "__main__":
    asyncio.run(main())
