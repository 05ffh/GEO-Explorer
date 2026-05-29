import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.organization import Organization
from src.models.brand import Brand
from src.models.user import User
from src.models.gt_candidate import GroundTruthCandidate


def _clear_overrides():
    app.dependency_overrides = {}


async def _setup_auth(db_session):
    """Create test org+user and set up dependency overrides. Returns (org, user)."""
    _clear_overrides()
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()

    user = User(organization_id=org.id, email="test@test.com", name="Test", role="admin", password_hash="test_hash")
    db_session.add(user)
    await db_session.commit()

    from src.api.deps import get_db, get_current_user

    async def override_db():
        yield db_session

    async def override_user():
        return user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return org, user


@pytest.mark.asyncio
async def test_list_gt_candidates_empty(db_session):
    """Test listing GT candidates returns empty list with high_risk_fields."""
    org, _user = await _setup_auth(db_session)

    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/brands/{brand.id}/gt-candidates")
        assert response.status_code == 200
        data = response.json()
        assert data["candidates"] == []
        assert "high_risk_fields" in data


@pytest.mark.asyncio
async def test_review_and_promote_flow(db_session):
    """Full flow: create candidate → review → promote to active GT."""
    org, _user = await _setup_auth(db_session)

    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    candidate = GroundTruthCandidate(
        organization_id=org.id,
        brand_id=brand.id,
        candidate_json={
            "official_name": "TestBrand",
            "aliases": ["TB"],
            "industry": "Technology",
            "category": "SaaS",
            "positioning": "Leading platform",
            "core_products": "Platform A",
            "target_users": "Enterprises",
            "core_scenarios": "Data analysis",
            "key_differentiators": "Fast",
            "official_domains": "test.com",
            "source_of_truth_by_field": {},
        },
        overall_confidence="medium",
        status="pending_review",
    )
    db_session.add(candidate)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        field_reviews = [
            {"field_name": f, "action": "accept", "new_value": None}
            for f in candidate.candidate_json.keys()
        ]
        response = await client.post(
            f"/api/gt-candidates/{candidate.id}/review",
            json={"field_reviews": field_reviews, "notes": "Looks good"},
        )
        assert response.status_code == 200

        response = await client.post(f"/api/gt-candidates/{candidate.id}/promote")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "promoted"
        assert "gt_version_id" in data


@pytest.mark.asyncio
async def test_promote_fails_missing_required_fields(db_session):
    """Promotion should fail when required fields are incomplete."""
    org, _user = await _setup_auth(db_session)

    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    candidate = GroundTruthCandidate(
        organization_id=org.id,
        brand_id=brand.id,
        candidate_json={"official_name": "TestBrand"},
        overall_confidence="low",
        status="pending_review",
    )
    db_session.add(candidate)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/gt-candidates/{candidate.id}/promote")
        assert response.status_code == 400
        assert "Missing required fields" in response.json()["detail"]


@pytest.mark.asyncio
async def test_promote_fails_high_risk_uncertain(db_session):
    """Promotion requires high-risk fields to not be marked UNCERTAIN."""
    org, _user = await _setup_auth(db_session)

    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    # Has all required fields but a high-risk field (positioning) is UNCERTAIN
    candidate = GroundTruthCandidate(
        organization_id=org.id,
        brand_id=brand.id,
        candidate_json={
            "official_name": "TestBrand",
            "aliases": ["TB"],
            "industry": "Technology",
            "category": "SaaS",
            "positioning": "[UNCERTAIN] Might be a platform",
            "core_products": "Platform A",
            "target_users": "Enterprises",
            "core_scenarios": "Data analysis",
            "key_differentiators": "Fast",
            "official_domains": "test.com",
            "source_of_truth_by_field": {},
        },
        overall_confidence="medium",
        status="pending_review",
    )
    db_session.add(candidate)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/gt-candidates/{candidate.id}/promote")
        assert response.status_code == 400
        assert "High-risk fields" in response.json()["detail"]
