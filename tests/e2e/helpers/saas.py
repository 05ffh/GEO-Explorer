"""E2E test helpers — create org/user/key scaffolding."""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.organization import Organization
from src.models.user import User
from src.models.brand import Brand
from src.models.saas import PlanDefinition, OrgSubscription, ApiKey
from src.saas.api_key_auth import generate_api_key


async def create_org_with_user(db: AsyncSession, org_name: str = "E2E Org",
                                 email: str = "e2e@test.com", role: str = "owner") -> tuple:
    """Create org + user, returning (org, user)."""
    org = Organization(name=org_name, plan="free")
    db.add(org)
    await db.commit()
    user = User(organization_id=org.id, email=email, name="E2E User",
                role=role, password_hash="hash")
    db.add(user)
    await db.commit()
    return org, user


async def seed_plans(db: AsyncSession):
    """Ensure seed plans exist for E2E tests."""
    from src.seed.saas_seed import seed_plans as _seed
    await _seed(db)


async def create_api_key(db: AsyncSession, org_id, user_id, scopes=None) -> tuple[str, ApiKey]:
    """Create an API key and return (full_key, api_key_obj)."""
    raw, prefix, key_hash = generate_api_key("test")
    key = ApiKey(organization_id=org_id, user_id=user_id, name="E2E Key",
                 key_type="test", key_prefix=prefix, key_hash=key_hash,
                 scopes_json=scopes or ["brands:read", "brands:write"], is_active=True)
    db.add(key)
    await db.commit()
    return prefix + raw, key


async def create_brand(db: AsyncSession, org_id, user_id, name: str = "E2E Brand") -> Brand:
    """Create a test brand."""
    brand = Brand(organization_id=org_id, name=name, industry="Tech", created_by=user_id)
    db.add(brand)
    await db.commit()
    return brand
