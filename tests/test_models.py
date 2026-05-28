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
