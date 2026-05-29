import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from src.config import settings
from src.models.base import Base

TRUNCATE_ALL = (
    "TRUNCATE TABLE action_themes, content_packages, gt_reviews, gt_evidences, gt_candidates, "
    "insight_summaries, hallucination_results, api_usage_logs, query_results, "
    "metrics_snapshots, action_plans, content_library, collection_runs, "
    "competitor_sets, ground_truth_versions, prompt_versions, query_templates, "
    "brands, users, organizations CASCADE"
)


@pytest_asyncio.fixture(scope="session")
async def engine():
    e = create_async_engine(settings.test_database_url, poolclass=NullPool)
    async with e.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    conn = await engine.connect()
    await conn.execute(text(TRUNCATE_ALL))
    await conn.commit()
    await conn.close()
