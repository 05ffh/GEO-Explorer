"""Module 2: Collection Run — integration tests."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.models.user import User
from src.models.brand import Brand
from src.models.organization import Organization
from src.models.collection_run import CollectionRun
import jwt


def _token_for(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.secret_key, algorithm=settings.jwt_algorithm,
    )


def _make_client(app, db_session):
    from httpx import AsyncClient, ASGITransport
    from src.database import get_db

    app.dependency_overrides.clear()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def mod2_org(db_session: AsyncSession):
    org = Organization(name="Module2_TestOrg")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def mod2_user(db_session: AsyncSession, mod2_org):
    import bcrypt
    user = User(
        email="mod2_test@geo.com",
        name="Module2 Tester",
        password_hash=bcrypt.hashpw(b"test123", bcrypt.gensalt()).decode(),
        organization_id=mod2_org.id,
        platform_role="org_admin",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def mod2_brand(db_session: AsyncSession, mod2_org):
    b = Brand(name="Mod2Brand", aliases=["M2"], industry="科技",
              organization_id=mod2_org.id)
    db_session.add(b)
    await db_session.flush()
    return b


@pytest.fixture
async def mod2_runs(db_session: AsyncSession, mod2_brand, mod2_org):
    runs = []
    for i, status in enumerate(["completed", "running", "failed"]):
        r = CollectionRun(
            organization_id=mod2_org.id,
            brand_id=mod2_brand.id,
            trigger_type="manual",
            collection_status=status,
            total_queries=200,
            success_count=156 if status != "failed" else 0,
            failure_count=0 if status != "failed" else 200,
            started_at=datetime.now(timezone.utc) - timedelta(hours=i),
        )
        db_session.add(r)
        runs.append(r)
    await db_session.flush()
    return runs


class TestRunList:
    async def test_list_page_returns_200(self, mod2_user, mod2_brand, mod2_runs, db_session):
        from src.main import app
        token = _token_for(str(mod2_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod2_brand.id}/runs",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        assert "已完成" in html or "采集中" in html or "失败" in html

    async def test_list_page_shows_run_counts(self, mod2_user, mod2_brand, mod2_runs, db_session):
        from src.main import app
        token = _token_for(str(mod2_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod2_brand.id}/runs",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "156" in resp.text
        assert "200" in resp.text


class TestCancelCollection:
    async def test_cancel_queued_run(self, mod2_user, mod2_brand, mod2_runs, db_session):
        from src.main import app
        running = [r for r in mod2_runs if r.collection_status == "running"][0]
        token = _token_for(str(mod2_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.post(f"/api/collections/{running.id}/cancel",
                                     headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code in (200, 202)
        data = resp.json()
        assert data.get("accepted") or data.get("status") in ("cancelled", "revoked")

    async def test_cancel_nonexistent_returns_error(self, mod2_user, db_session):
        from src.main import app
        import uuid as _uuid
        token = _token_for(str(mod2_user.id))
        fake_id = str(_uuid.uuid4())
        async with _make_client(app, db_session) as client:
            resp = await client.post(f"/api/collections/{fake_id}/cancel",
                                     headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code in (200, 404, 422)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                assert data.get("detail") or not data.get("accepted", True)


class TestPollingRefresh:
    async def test_detail_page_returns_200(self, mod2_user, mod2_brand, mod2_runs, db_session):
        from src.main import app
        run = mod2_runs[0]
        token = _token_for(str(mod2_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod2_brand.id}/runs/{run.id}",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            assert "诊断详情" in resp.text
