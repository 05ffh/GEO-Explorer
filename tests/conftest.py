import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.config import settings
from src.models.base import Base


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Session-scoped async engine — reused across all tests."""
    e = create_async_engine(settings.test_database_url)
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """Yield a clean database session with tables created/dropped per test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
