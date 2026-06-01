"""Data export/deletion page API tests (Task 4 — P0-8)."""
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.api.deps import get_db, get_current_user
from src.models.organization import Organization
from src.models.user import User
from src.models.brand import Brand
from src.models.saas import DataExport, DataDeletionRequest, DeletionReceipt


def _clear_overrides():
    app.dependency_overrides = {}


from datetime import datetime, timezone, timedelta

async def _setup(db_session, role="owner"):
    _clear_overrides()
    org = Organization(name="DataOrg")
    db_session.add(org); await db_session.commit()
    user = User(organization_id=org.id, email="d@t.com", name="T", role=role, password_hash="x")
    db_session.add(user); await db_session.commit()

    async def override_db(): yield db_session
    async def override_user(): return user
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return org, user


@pytest.mark.asyncio
async def test_list_exports(db_session):
    org, user = await _setup(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/saas/data-exports")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_export(db_session):
    org, user = await _setup(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/saas/data-exports", json={"scope": "organization", "format": "json"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_revoke_export(db_session):
    org, user = await _setup(db_session)
    exp = DataExport(organization_id=org.id, user_id=user.id, scope="organization",
                     format="json", status="completed",
                     expires_at=datetime.now(timezone.utc) + timedelta(hours=72))
    db_session.add(exp); await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/saas/data-exports/{exp.id}/revoke")
        assert resp.status_code == 200
        assert resp.json()["revoked"] == True


@pytest.mark.asyncio
async def test_create_deletion_request(db_session):
    org, user = await _setup(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/saas/data-deletion-requests",
                                 json={"scope": "brand", "reason": "测试删除"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "requested"


@pytest.mark.asyncio
async def test_cancel_deletion(db_session):
    org, user = await _setup(db_session)
    dr = DataDeletionRequest(organization_id=org.id, requested_by=user.id,
                             scope="brand", status="requested", reason="test")
    db_session.add(dr); await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(f"/api/saas/data-deletion-requests/{dr.id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] == True


@pytest.mark.asyncio
async def test_dry_run_deletion(db_session):
    org, user = await _setup(db_session)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/saas/data-deletion-requests/dry-run",
                                 json={"scope": "brand"})
        assert resp.status_code == 200
        assert "affected_tables" in resp.json()


@pytest.mark.asyncio
async def test_receipt_viewable_after_completion(db_session):
    org, user = await _setup(db_session)
    dr = DataDeletionRequest(organization_id=org.id, requested_by=user.id,
                             scope="brand", status="completed_with_warnings")
    db_session.add(dr); await db_session.commit()

    receipt = DeletionReceipt(
        deletion_request_id=dr.id, organization_id=org.id, scope="brand",
        requested_by=user.id, approved_by=user.id,
        started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc),
        affected_tables_json={}, deleted_counts_json={},
        receipt_hash="abc123",
    )
    db_session.add(receipt); await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/saas/data-deletion-requests/{dr.id}/receipt")
        assert resp.status_code == 200
        assert resp.json()["receipt_hash"] == "abc123"
