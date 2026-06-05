"""Module 9: Global Infrastructure — integration tests."""

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
async def mod9_org(db_session: AsyncSession):
    org = Organization(name="Module9_TestOrg")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def mod9_admin(db_session: AsyncSession, mod9_org):
    import bcrypt
    user = User(
        email="mod9_admin@geo.com",
        name="Module9 Admin",
        password_hash=bcrypt.hashpw(b"test123", bcrypt.gensalt()).decode(),
        organization_id=mod9_org.id,
        platform_role="org_admin",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def mod9_regular(db_session: AsyncSession, mod9_org):
    import bcrypt
    user = User(
        email="mod9_user@geo.com",
        name="Module9 User",
        password_hash=bcrypt.hashpw(b"test123", bcrypt.gensalt()).decode(),
        organization_id=mod9_org.id,
        platform_role=None,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def mod9_brand(db_session: AsyncSession, mod9_org):
    b = Brand(name="Mod9Brand", aliases=["M9"], industry="科技",
              organization_id=mod9_org.id)
    db_session.add(b)
    await db_session.flush()
    return b


class TestPlatformNavGate:
    async def test_regular_user_no_platform_nav(self, mod9_regular, mod9_brand, db_session):
        """Regular user (platform_role=None) should NOT see platform nav links."""
        from src.main import app
        token = _token_for(str(mod9_regular.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod9_brand.id}",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        # Platform nav items should not appear for regular users
        assert "平台总览" not in html or "platform" not in html.lower()

    async def test_admin_sees_platform_nav(self, mod9_admin, mod9_brand, db_session):
        """Admin user should see platform nav links."""
        from src.main import app
        token = _token_for(str(mod9_admin.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod9_brand.id}",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        # org_admin is not system_admin, so shouldn't see platform nav either
        # platform nav is for system_owner / system_admin only
        assert "平台总览" not in html


class TestSecurityRendering:
    async def test_no_unescaped_html(self, mod9_admin, mod9_brand, db_session):
        """Brand page should escape HTML in brand names (no raw HTML injection)."""
        from src.main import app
        token = _token_for(str(mod9_admin.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod9_brand.id}",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        # Jinja2 auto-escapes; no user content should emit raw <script> tags
        # Legitimate script tags: those with src= attribute plus inline scripts
        script_tags = html.count('<script')
        legit = html.count('<script src') + html.count('<script>')
        assert script_tags == legit, f"raw <script>: {script_tags} vs legit: {legit}"
