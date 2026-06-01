"""Registration tests (Task 5 — P0-6/P0-7)."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from src.main import app
from src.api.deps import get_db
from src.models.organization import Organization
from src.models.saas import PlanDefinition


def _clear_overrides():
    app.dependency_overrides = {}


@pytest.mark.asyncio
async def test_register_success(db_session):
    """Full registration creates org + user + subscription."""
    _clear_overrides()
    # Seed free plan first
    from src.seed.saas_seed import seed_plans
    await seed_plans(db_session)

    async def override_db():
        yield db_session
    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/saas/register", json={
            "email": "newuser@test.com", "password": "password123",
            "organization_name": "NewOrg", "accepted_terms": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "free"
        assert "organization_id" in data
        assert "user_id" in data
        assert data["email_verified"] == False


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(db_session):
    """Duplicate email returns 409."""
    _clear_overrides()
    from src.seed.saas_seed import seed_plans
    await seed_plans(db_session)

    async def override_db(): yield db_session
    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First registration
        await client.post("/api/saas/register", json={
            "email": "dup@test.com", "password": "password123",
            "organization_name": "Org1", "accepted_terms": True,
        })
        # Duplicate
        resp = await client.post("/api/saas/register", json={
            "email": "dup@test.com", "password": "password123",
            "organization_name": "Org2", "accepted_terms": True,
        })
        assert resp.status_code == 409


@pytest.mark.asyncio
async def test_register_requires_terms(db_session):
    """Registration without accepted_terms returns 400."""
    _clear_overrides()
    from src.seed.saas_seed import seed_plans
    await seed_plans(db_session)

    async def override_db(): yield db_session
    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/saas/register", json={
            "email": "test@test.com", "password": "password123",
            "organization_name": "Org", "accepted_terms": False,
        })
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_rejects_short_password(db_session):
    """Password < 8 chars returns 400."""
    _clear_overrides()
    from src.seed.saas_seed import seed_plans
    await seed_plans(db_session)

    async def override_db(): yield db_session
    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/saas/register", json={
            "email": "test@test.com", "password": "123",
            "organization_name": "Org", "accepted_terms": True,
        })
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_rejects_disposable_email(db_session):
    """Disposable email domains are rejected."""
    _clear_overrides()
    from src.seed.saas_seed import seed_plans
    await seed_plans(db_session)

    async def override_db(): yield db_session
    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/saas/register", json={
            "email": "spam@mailinator.com", "password": "password123",
            "organization_name": "Org", "accepted_terms": True,
        })
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_user_model_has_email_verified(db_session):
    """User model has the email_verified field."""
    from src.models.user import User
    assert hasattr(User, "email_verified")
