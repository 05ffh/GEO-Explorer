"""E2E test fixtures — shared between API and Browser E2E tests."""
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from src.config import settings
from src.models.base import Base

E2E_TRUNCATE = (
    "TRUNCATE TABLE api_key_usage_logs, org_invites, org_subscriptions, api_keys, "
    "data_exports, data_deletion_requests, deletion_receipts, "
    "emergency_pauses, feature_flag_overrides, feature_flags, "
    "audit_logs, plan_change_requests, plan_definitions, usage_meter_definitions, "
    "publish_attempts, publish_events, publish_requests, publish_batches, publish_targets, "
    "report_artifacts, action_themes, content_packages, hallucination_results, "
    "query_results, collection_runs, metric_snapshots, "
    "brands, users, organizations CASCADE"
)


@pytest_asyncio.fixture(scope="session")
async def e2e_engine():
    e = create_async_engine(settings.test_database_url, poolclass=NullPool)
    async with e.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def e2e_db(e2e_engine):
    """Isolated DB session for each E2E test."""
    factory = async_sessionmaker(e2e_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    conn = await e2e_engine.connect()
    await conn.execute(text(E2E_TRUNCATE))
    await conn.commit()
    await conn.close()
