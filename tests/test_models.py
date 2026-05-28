import pytest
from src.models.organization import Organization
from src.models.user import User


@pytest.mark.asyncio
async def test_create_organization(db_session):
    org = Organization(name="Test Corp", plan="pro")
    db_session.add(org)
    await db_session.commit()
    assert org.id is not None


@pytest.mark.asyncio
async def test_create_user(db_session):
    org = Organization(name="Test Corp")
    db_session.add(org)
    await db_session.commit()
    user = User(organization_id=org.id, email="a@b.com", name="Test", role="admin", password_hash="hash")
    db_session.add(user)
    await db_session.commit()
    assert user.organization_id == org.id


@pytest.mark.asyncio
async def test_brand_and_gt_no_circular_fk(db_session):
    org = Organization(name="TC")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand)
    await db_session.commit()
    assert brand.id is not None

    gt = GroundTruthVersion(
        brand_id=brand.id, version=1,
        ground_truth_json={"official_name": "TestBrand", "industry": "Tech",
                           "positioning": "Test tool", "official_domains": ["test.com"]},
        status="active"
    )
    db_session.add(gt)
    await db_session.commit()
    assert gt.id is not None
