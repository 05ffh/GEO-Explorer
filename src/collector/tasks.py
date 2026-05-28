import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from src.celery_app import app
from src.config import settings
from src.collector.engine import run_collection
from src.models.brand import Brand

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@app.task
def collect_brand_task(brand_id: str, org_id: str):
    async def _run():
        async with SessionLocal() as db:
            return await run_collection(
                uuid.UUID(brand_id), uuid.UUID(org_id), db, trigger_type="manual",
            )

    return asyncio.run(_run())


@app.task
def weekly_collect():
    async def _run():
        async with SessionLocal() as db:
            brands = (await db.execute(select(Brand))).scalars().all()
            if not brands:
                return "no brands found"
            for brand in brands:
                await run_collection(
                    brand.id, brand.organization_id, db, trigger_type="scheduled",
                )
            return f"collected {len(brands)} brands"

    return asyncio.run(_run())
