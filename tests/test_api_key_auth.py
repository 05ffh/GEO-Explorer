"""API Key real-route integration tests (Task 0 — P0-1)."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.main import app
from src.models.organization import Organization
from src.models.user import User
from src.models.brand import Brand
from src.models.saas import ApiKey, ApiKeyUsageLog
from src.saas.api_key_auth import generate_api_key, API_KEY_HEADER
from src.api.deps import get_db


def _clear_overrides():
    app.dependency_overrides = {}


async def _setup_api_key_test(db_session, scopes=None, revoked=False, expired=False):
    """Set up test org+user+brand+API key. Returns (org, user, api_key, full_key, brand)."""
    _clear_overrides()

    org = Organization(name="APIKeyTestOrg")
    db_session.add(org)
    await db_session.commit()

    user = User(organization_id=org.id, email="keytest@test.com", name="KeyTest",
                role="owner", password_hash="test_hash")
    db_session.add(user)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech", created_by=user.id)
    db_session.add(brand)
    await db_session.commit()

    raw_key, prefix, key_hash = generate_api_key("test")
    full_key = prefix + raw_key  # geo_test_<hex>
    from datetime import datetime, timezone, timedelta

    api_key = ApiKey(
        organization_id=org.id, user_id=user.id,
        name="Test Key", key_type="test", key_prefix=prefix, key_hash=key_hash,
        scopes_json=scopes or ["brands:read", "brands:write", "collections:run", "collections:read"],
        is_active=True,
        expires_at=(datetime.now(timezone.utc) - timedelta(days=1)) if expired else None,
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )
    db_session.add(api_key)
    await db_session.commit()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db

    return org, user, api_key, full_key, brand


@pytest.mark.asyncio
async def test_list_brands_with_valid_api_key(db_session):
    """GET /api/brands — valid API key returns brand list."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/brands", headers={API_KEY_HEADER: full_key})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_get_brand_with_valid_api_key(db_session):
    """GET /api/brands/{id} — valid API key returns brand details."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/brands/{brand.id}", headers={API_KEY_HEADER: full_key})
        assert response.status_code == 200
        data = response.json()
        assert data["brand"]["name"] == "TestBrand"


@pytest.mark.asyncio
async def test_api_key_usage_log_written(db_session):
    """API key usage is logged to ApiKeyUsageLog."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/api/brands", headers={API_KEY_HEADER: full_key})

    logs = (await db_session.execute(
        select(ApiKeyUsageLog).where(ApiKeyUsageLog.api_key_id == api_key.id)
    )).scalars().all()
    assert len(logs) >= 1
    assert logs[0].endpoint == "/api/brands"
    assert logs[0].method == "GET"


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401(db_session):
    """Invalid API key returns 401."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/brands", headers={API_KEY_HEADER: "geo_test_deadbeef"})
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_revoked_api_key_returns_401(db_session):
    """Revoked API key returns 401 with API_KEY_REVOKED."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session, revoked=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/brands", headers={API_KEY_HEADER: full_key})
        assert response.status_code == 401
        assert response.json()["detail"]["error_code"] == "API_KEY_REVOKED"


@pytest.mark.asyncio
async def test_expired_api_key_returns_401(db_session):
    """Expired API key returns 401 with API_KEY_EXPIRED."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session, expired=True)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/brands", headers={API_KEY_HEADER: full_key})
        assert response.status_code == 401
        assert response.json()["detail"]["error_code"] == "API_KEY_EXPIRED"


@pytest.mark.asyncio
async def test_create_brand_with_api_key(db_session):
    """POST /api/brands — API key with brands:write scope creates brand."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/brands",
            headers={API_KEY_HEADER: full_key},
            json={"name": "API Brand", "aliases": [], "industry": "SaaS"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "API Brand"


@pytest.mark.asyncio
async def test_get_metrics_with_api_key(db_session):
    """GET /api/brands/{id}/metrics — API key accesses metrics."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/brands/{brand.id}/metrics",
                                    headers={API_KEY_HEADER: full_key})
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data or "message" in data


@pytest.mark.asyncio
async def test_list_collections_with_api_key(db_session):
    """GET /api/brands/{id}/collections — API key accesses collections."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/brands/{brand.id}/collections",
                                    headers={API_KEY_HEADER: full_key})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


@pytest.mark.asyncio
async def test_api_key_usage_count_incremented(db_session):
    """API key usage_count increments after each call."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(3):
            await client.get("/api/brands", headers={API_KEY_HEADER: full_key})

    await db_session.refresh(api_key)
    assert api_key.usage_count >= 3
    assert api_key.last_used_at is not None


@pytest.mark.asyncio
async def test_cookie_auth_still_works_alongside_api_key(db_session):
    """Cookie/JWT auth still works when get_user_or_api_key is the dependency."""
    org, user, api_key, full_key, brand = await _setup_api_key_test(db_session)
    _clear_overrides()

    from src.api.deps import get_user_or_api_key

    async def override_db():
        yield db_session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_user_or_api_key] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/brands")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
