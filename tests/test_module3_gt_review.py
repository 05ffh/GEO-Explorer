"""Module 3: GT Review — integration tests."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.models.user import User
from src.models.brand import Brand
from src.models.organization import Organization
from src.models.gt_candidate import GroundTruthCandidate
from src.models.gt_evidence import GroundTruthEvidence
from src.models.ground_truth import GroundTruthVersion
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
async def mod3_org(db_session: AsyncSession):
    org = Organization(name="Module3_TestOrg")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def mod3_user(db_session: AsyncSession, mod3_org):
    import bcrypt
    user = User(
        email="mod3_test@geo.com",
        name="Module3 Tester",
        password_hash=bcrypt.hashpw(b"test123", bcrypt.gensalt()).decode(),
        organization_id=mod3_org.id,
        platform_role="org_admin",
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def mod3_brand(db_session: AsyncSession, mod3_org):
    b = Brand(name="Mod3Brand", aliases=["M3"], industry="科技",
              organization_id=mod3_org.id)
    db_session.add(b)
    await db_session.flush()
    return b


@pytest.fixture
async def mod3_gt_data(db_session: AsyncSession, mod3_brand, mod3_org):
    # Active GT
    gt = GroundTruthVersion(
        brand_id=mod3_brand.id, version=1,
        ground_truth_json={"official_name": "Mod3Brand", "category": "SaaS", "positioning": "测试品牌"},
        status="active",
    )
    db_session.add(gt)
    await db_session.flush()

    # Candidate GT (v2)
    candidate = GroundTruthCandidate(
        brand_id=mod3_brand.id,
        organization_id=mod3_org.id,
        candidate_json={
            "official_name": "Mod3Brand Inc",
            "category": "Technology",
            "positioning": "测试品牌新定位",
            "core_products": "数据分析平台",
        },
        status="pending_review",
    )
    db_session.add(candidate)
    await db_session.flush()

    # Evidence for candidate fields
    evidence = [
        GroundTruthEvidence(
            candidate_id=candidate.id, field_name="official_name",
            value="Mod3Brand Inc", source_type="web", source_name="官网",
            source_url="https://mod3.example.com/about", excerpt="Mod3Brand Inc is a leading...",
            source_tier="A", confidence="high",
        ),
        GroundTruthEvidence(
            candidate_id=candidate.id, field_name="category",
            value="Technology", source_type="web", source_name="天眼查",
            source_url="https://tianyancha.example.com", excerpt="经营范围: Technology...",
            source_tier="B", confidence="medium",
        ),
        GroundTruthEvidence(
            candidate_id=candidate.id, field_name="core_products",
            value="数据分析平台", source_type="ai", source_name="DeepSeek",
            source_url="", excerpt="数据分析平台是核心产品...",
            source_tier="C", confidence="low",
        ),
    ]
    for ev in evidence:
        db_session.add(ev)
    await db_session.flush()
    return {"gt": gt, "candidate": candidate, "evidence": evidence}


class TestGTSourceDetail:
    async def test_gt_review_page_has_source_info(self, mod3_user, mod3_brand, mod3_gt_data, db_session):
        from src.main import app
        token = _token_for(str(mod3_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod3_brand.id}/gt-review",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        # Should show source tier badges and source names
        assert "官网" in html or "天眼查" in html or "DeepSeek" in html

    async def test_gt_review_shows_source_urls(self, mod3_user, mod3_brand, mod3_gt_data, db_session):
        from src.main import app
        token = _token_for(str(mod3_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod3_brand.id}/gt-review",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        assert "mod3.example.com" in html or "tianyancha.example.com" in html


class TestGTVersionCompare:
    async def test_gt_compare_page_returns_200(self, mod3_user, mod3_brand, mod3_gt_data, db_session):
        from src.main import app
        token = _token_for(str(mod3_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod3_brand.id}/gt-compare",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        assert "Mod3Brand" in html

    async def test_gt_compare_shows_diff(self, mod3_user, mod3_brand, mod3_gt_data, db_session):
        from src.main import app
        token = _token_for(str(mod3_user.id))
        async with _make_client(app, db_session) as client:
            resp = await client.get(f"/brands/{mod3_brand.id}/gt-compare",
                                    headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        html = resp.text
        # Should show changed fields
        assert "category" in html
        assert "positioning" in html or "core_products" in html
