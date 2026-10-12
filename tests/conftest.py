import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from src.config import settings
from src.models.base import Base

TRUNCATE_ALL = (
    "TRUNCATE TABLE search_results, measurement_snapshots, "
    "collection_runs, brands, organizations CASCADE"
)


@pytest_asyncio.fixture(scope="session")
async def engine():
    e = create_async_engine(settings.test_database_url, poolclass=NullPool)
    async with e.connect() as conn:
        # create_all 不 alter 已存在表 → 字段有变更的表 drop 重建，确保测试库 schema 最新：
        # measurement_snapshots（唯一约束）/ search_results（raw_content 列）/
        # collection_runs（gt_facts_json 列 + 去 ground_truth_version_id，2026-09-16）/
        # brands（去 users FK 列 created_by/updated_by，2026-10-12 旧系统清理）
        for _t in ("measurement_snapshots", "search_results", "collection_runs", "brands"):
            await conn.execute(text(f"DROP TABLE IF EXISTS {_t} CASCADE"))
        await conn.commit()
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
