"""Module 1: Brand Management — integration tests."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.models.user import User
from src.models.brand import Brand
from src.models.organization import Organization
import jwt


def _token_for(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def _make_client(app, db_session):
    from httpx import AsyncClient, ASGITransport
    from src.database import get_db

    app.dependency_overrides.clear()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def test_org(db_session: AsyncSession):
    org = Organization(name="Module1_TestOrg")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def test_user(db_session: AsyncSession, test_org):
    import bcrypt
    user = User(
        email="mod1_test@geo.com",
        name="Module1 Tester",
        password_hash=bcrypt.hashpw(b"test123", bcrypt.gensalt()).decode(),
        organization_id=test_org.id,
        platform_role="org_admin",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_brands(db_session: AsyncSession, test_org):
    brands = []
    for i in range(3):
        b = Brand(
            name=f"TestBrand_{i}",
            aliases=[f"TB{i}"],
            industry="restaurant_chain" if i < 2 else "technology",
            organization_id=test_org.id,
        )
        db_session.add(b)
        brands.append(b)
    await db_session.flush()
    return brands


class TestBrandList:
    async def test_list_returns_200(self, test_user, test_brands, db_session):
        from src.main import app
        token = _token_for(str(test_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get("/brands", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        assert "TestBrand_0" in html
        assert "TestBrand_1" in html
        assert "TestBrand_2" in html

    async def test_search_filter(self, test_user, test_brands, db_session):
        from src.main import app
        token = _token_for(str(test_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get("/brands?q=TestBrand_1",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "TestBrand_1" in resp.text

    async def test_empty_state(self, test_user, db_session):
        from src.main import app
        token = _token_for(str(test_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get("/brands", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200


class TestBrandEdit:
    async def test_edit_fragment_returns_form(self, test_user, test_brands, db_session):
        from src.main import app
        brand = test_brands[0]
        token = _token_for(str(test_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{brand.id}/edit",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        assert brand.name in html


class TestGTCollectButton:
    async def test_dashboard_has_gt_button(self, test_user, test_brands, db_session):
        from src.main import app
        brand = test_brands[0]
        token = _token_for(str(test_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{brand.id}",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        assert '采集' in html or 'GT' in html
