"""Platform API tests (Task 3 — P0-1/P0-2/P0-3)."""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.main import app
from src.api.deps import get_db, get_current_user
from src.models.organization import Organization
from src.models.user import User
from src.models.brand import Brand
from src.models.saas import DataDeletionRequest
from src.view_models.platform import build_platform_vm


def _clear_overrides():
    app.dependency_overrides = {}


async def _setup_platform_test(db_session, platform_role="system_owner"):
    """Create org+platform user and override auth. Returns (org, user)."""
    _clear_overrides()
    org = Organization(name="PlatformOrg")
    db_session.add(org)
    await db_session.commit()

    user = User(organization_id=org.id, email=f"{platform_role}@test.com",
                name="Admin", role="admin", platform_role=platform_role,
                password_hash="test_hash")
    db_session.add(user)
    await db_session.commit()

    async def override_db():
        yield db_session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return org, user


@pytest.mark.asyncio
async def test_platform_overview(db_session):
    """GET /api/platform/overview returns platform stats."""
    org, user = await _setup_platform_test(db_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/platform/overview")
        assert response.status_code == 200
        data = response.json()
        assert "org_count" in data
        assert "active_org_count" in data
        assert "brand_count" in data
        assert "user_count" in data
        assert "active_api_key_count" in data
        assert data["can_view_internal_cost"] == True


@pytest.mark.asyncio
async def test_system_admin_cannot_view_plans(db_session):
    """system_admin accessing plans gets 403."""
    org, user = await _setup_platform_test(db_session, platform_role="system_admin")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Can see overview
        resp = await client.get("/api/platform/overview")
        assert resp.status_code == 200

        # Cannot create plans (system_owner only)
        resp = await client.post("/api/platform/plans", json={"name": "test"})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_system_admin_cannot_approve_deletion(db_session):
    """system_admin accessing deletion approval gets 403."""
    org, user = await _setup_platform_test(db_session, platform_role="system_admin")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/platform/data-deletion-requests")
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_system_owner_can_list_deletion_requests(db_session):
    """system_owner can list pending deletion requests."""
    org, user = await _setup_platform_test(db_session)

    # Create a deletion request
    brand = Brand(organization_id=org.id, name="TB", industry="Tech", created_by=user.id)
    db_session.add(brand)
    await db_session.commit()

    dr = DataDeletionRequest(
        organization_id=org.id, requested_by=user.id,
        scope="brand", brand_id=brand.id, status="requested",
    )
    db_session.add(dr)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/platform/data-deletion-requests")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1


@pytest.mark.asyncio
async def test_reject_deletion_requires_reason(db_session):
    """Rejecting a deletion without reason returns 400."""
    org, user = await _setup_platform_test(db_session)

    brand = Brand(organization_id=org.id, name="TB", industry="Tech", created_by=user.id)
    db_session.add(brand)
    await db_session.commit()

    dr = DataDeletionRequest(
        organization_id=org.id, requested_by=user.id,
        scope="brand", brand_id=brand.id, status="requested",
    )
    db_session.add(dr)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/platform/data-deletion-requests/{dr.id}/reject",
            json={"reason": ""},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_approve_deletion_requires_reason(db_session):
    """Approving a deletion without reason returns 400."""
    org, user = await _setup_platform_test(db_session)

    brand = Brand(organization_id=org.id, name="TB", industry="Tech", created_by=user.id)
    db_session.add(brand)
    await db_session.commit()

    dr = DataDeletionRequest(
        organization_id=org.id, requested_by=user.id,
        scope="brand", brand_id=brand.id, status="requested",
    )
    db_session.add(dr)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/platform/data-deletion-requests/{dr.id}/approve",
            json={"reason": ""},
        )
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_dry_run_deletion(db_session):
    """Dry-run returns affected table estimates."""
    org, user = await _setup_platform_test(db_session)

    brand = Brand(organization_id=org.id, name="TB", industry="Tech", created_by=user.id)
    db_session.add(brand)
    await db_session.commit()

    dr = DataDeletionRequest(
        organization_id=org.id, requested_by=user.id,
        scope="brand", brand_id=brand.id, status="requested",
    )
    db_session.add(dr)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/platform/data-deletion-requests/{dr.id}/dry-run",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "affected_tables" in data
        assert "estimated_delete_counts" in data
        assert "retained_items" in data


@pytest.mark.asyncio
async def test_platform_view_model_owner(db_session):
    """Platform VM: system_owner has all permissions."""
    org, user = await _setup_platform_test(db_session)
    vm = await build_platform_vm(user, db_session)

    assert vm["user"]["is_system_owner"] == True
    assert vm["user"]["is_system_admin"] == True
    assert vm["visible_pages"]["plans"] == True
    assert vm["visible_pages"]["data_deletion"] == True
    assert vm["actions"]["plans.create"] == True
    assert vm["actions"]["emergency_pause.global"] == True
    assert vm["actions"]["data_deletion.approve"] == True
    assert vm["actions"]["internal_cost.view"] == True


@pytest.mark.asyncio
async def test_platform_view_model_admin(db_session):
    """Platform VM: system_admin has limited permissions."""
    org, user = await _setup_platform_test(db_session, platform_role="system_admin")
    vm = await build_platform_vm(user, db_session)

    assert vm["user"]["is_system_owner"] == False
    assert vm["user"]["is_system_admin"] == True
    # Cannot see owner-only pages
    assert vm["visible_pages"]["plans"] == False
    assert vm["visible_pages"]["data_deletion"] == False
    # Can see shared pages
    assert vm["visible_pages"]["platform_overview"] == True
    assert vm["visible_pages"]["organizations"] == True
    # Actions restricted
    assert vm["actions"]["organizations.suspend"] == False
    assert vm["actions"]["feature_flags.edit"] == False
    assert vm["actions"]["feature_flags.view"] == True
    assert vm["actions"]["emergency_pause.global"] == False
    assert vm["actions"]["emergency_pause.organization"] == True
