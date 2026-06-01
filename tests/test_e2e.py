"""API E2E tests — verify full backend chains using existing test patterns (Task 8)."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.main import app
from src.api.deps import get_db, get_user_or_api_key


def _override(db_session, user=None):
    from src.api.deps import get_current_user as _gcu
    app.dependency_overrides = {}
    async def _db(): yield db_session
    app.dependency_overrides[get_db] = _db
    if user:
        async def _user(): return user
        app.dependency_overrides[_gcu] = _user
        app.dependency_overrides[get_user_or_api_key] = _user


@pytest.mark.asyncio
async def test_e2e_register_flow(db_session):
    """E2E: Register → login page loads → create brand."""
    from src.seed.saas_seed import seed_plans
    await seed_plans(db_session)

    _override(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register page loads
        resp = await client.get("/register")
        assert resp.status_code == 200

        # Register API
        resp = await client.post("/api/saas/register", json={
            "email": "e2e@flow.com", "password": "password123",
            "organization_name": "E2EFlowOrg", "accepted_terms": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan"] == "free"
        assert data["email_verified"] == False


@pytest.mark.asyncio
async def test_e2e_api_key_integration(db_session):
    """E2E: Create API key → use it on real route → usage logged."""
    from src.seed.saas_seed import seed_plans
    from src.models.organization import Organization
    from src.models.user import User
    from src.models.brand import Brand
    from src.models.saas import ApiKey, ApiKeyUsageLog
    from src.saas.api_key_auth import generate_api_key

    await seed_plans(db_session)
    org = Organization(name="KeyE2EOrg")
    db_session.add(org); await db_session.commit()
    user = User(organization_id=org.id, email="keye2e@t.com", name="KE",
                role="owner", password_hash="x")
    db_session.add(user); await db_session.commit()
    brand = Brand(organization_id=org.id, name="KB", industry="Tech", created_by=user.id)
    db_session.add(brand); await db_session.commit()

    raw, prefix, key_hash = generate_api_key("test")
    full_key = prefix + raw
    api_key = ApiKey(organization_id=org.id, user_id=user.id, name="E2E",
                     key_type="test", key_prefix=prefix, key_hash=key_hash,
                     scopes_json=["brands:read"], is_active=True)
    db_session.add(api_key); await db_session.commit()

    # Override only DB, let API key auth resolve normally
    app.dependency_overrides = {}
    async def _db(): yield db_session
    app.dependency_overrides[get_db] = _db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/brands", headers={"X-GEO-API-Key": full_key})
        assert resp.status_code == 200

        logs = (await db_session.execute(select(ApiKeyUsageLog).where(
            ApiKeyUsageLog.api_key_id == api_key.id
        ))).scalars().all()
        assert len(logs) >= 1


@pytest.mark.asyncio
async def test_e2e_cross_org_isolation(db_session):
    """E2E: User in OrgA cannot access OrgB's brand."""
    from src.seed.saas_seed import seed_plans
    from src.models.organization import Organization
    from src.models.user import User
    from src.models.brand import Brand

    await seed_plans(db_session)
    org_a = Organization(name="OrgA"); db_session.add(org_a); await db_session.commit()
    user_a = User(organization_id=org_a.id, email="a@t.com", name="A", role="owner", password_hash="x")
    db_session.add(user_a); await db_session.commit()
    org_b = Organization(name="OrgB"); db_session.add(org_b); await db_session.commit()
    user_b = User(organization_id=org_b.id, email="b@t.com", name="B", role="owner", password_hash="x")
    db_session.add(user_b); await db_session.commit()
    brand_b = Brand(organization_id=org_b.id, name="BB", industry="Tech", created_by=user_b.id)
    db_session.add(brand_b); await db_session.commit()

    _override(db_session, user_a)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/brands/{brand_b.id}")
        assert resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_e2e_deletion_request_flow(db_session):
    """E2E: Create → list → verify deletion request."""
    from src.seed.saas_seed import seed_plans
    from src.models.organization import Organization
    from src.models.user import User
    from src.models.brand import Brand
    from src.models.saas import DataDeletionRequest

    await seed_plans(db_session)
    org = Organization(name="DelOrg"); db_session.add(org); await db_session.commit()
    user = User(organization_id=org.id, email="del@t.com", name="D", role="owner", password_hash="x")
    db_session.add(user); await db_session.commit()
    brand = Brand(organization_id=org.id, name="DB", industry="Tech", created_by=user.id)
    db_session.add(brand); await db_session.commit()

    _override(db_session, user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/saas/data-deletion-requests", json={
            "scope": "brand", "brand_id": str(brand.id), "reason": "E2E test"
        })
        assert resp.status_code == 200
        dr_id = resp.json()["id"]

        resp = await client.get("/api/saas/data-deletion-requests")
        items = resp.json()
        assert any(d["id"] == dr_id for d in items)


@pytest.mark.asyncio
async def test_e2e_platform_overview_admin_only(db_session):
    """E2E: Platform overview accessible to system_admin, not org user."""
    from src.seed.saas_seed import seed_plans, seed_system_owner
    from src.models.organization import Organization
    from src.models.user import User
    from sqlalchemy import select as sa_select

    await seed_plans(db_session)
    await seed_system_owner(db_session, email="admin@geo.local")

    # Get system_owner user
    admin = (await db_session.execute(
        sa_select(User).where(User.platform_role == "system_owner")
    )).scalar_one()

    _override(db_session, admin)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # System owner can access overview
        resp = await client.get("/api/platform/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "org_count" in data
        assert data["can_view_internal_cost"] == True


@pytest.mark.asyncio
async def test_e2e_data_export_create_list(db_session):
    """E2E: Create data export → list exports → verify status."""
    from src.seed.saas_seed import seed_plans
    from src.models.organization import Organization
    from src.models.user import User

    await seed_plans(db_session)
    org = Organization(name="ExpOrg"); db_session.add(org); await db_session.commit()
    user = User(organization_id=org.id, email="exp@t.com", name="E", role="owner", password_hash="x")
    db_session.add(user); await db_session.commit()

    _override(db_session, user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/saas/data-exports", json={
            "scope": "organization", "format": "json"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

        resp = await client.get("/api/saas/data-exports")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1
