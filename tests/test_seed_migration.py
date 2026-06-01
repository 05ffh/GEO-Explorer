"""Migration/Seed idempotency tests (Task 1 — P0-10)."""
import pytest
from sqlalchemy import text

from src.seed.saas_seed import (
    seed_plans, seed_meters, seed_system_owner, migrate_existing_orgs, run_all_saas_seeds,
)


@pytest.mark.asyncio
async def test_seed_empty_database(db_session):
    """Empty DB: all seed functions succeed on first run."""
    result = await run_all_saas_seeds(db_session)
    assert result["plans"]["plans"] == "seeded"
    assert result["meters"]["meters"] == "seeded"
    assert result["system_owner"]["system_owner"] == "created"


@pytest.mark.asyncio
async def test_seed_plans_idempotent(db_session):
    """Seed plans twice — second run is skipped, no duplicates."""
    r1 = await seed_plans(db_session)
    assert r1["plans"] == "seeded"
    count1 = (await db_session.execute(text("SELECT COUNT(*) c FROM plan_definitions"))).scalar()

    r2 = await seed_plans(db_session)
    assert r2["plans"] == "skipped"
    count2 = (await db_session.execute(text("SELECT COUNT(*) c FROM plan_definitions"))).scalar()

    assert count1 == count2 == 3  # Free + Pro + Enterprise


@pytest.mark.asyncio
async def test_seed_meters_idempotent(db_session):
    """Seed meters twice — no duplicates."""
    r1 = await seed_meters(db_session)
    assert r1["meters"] == "seeded"
    count1 = (await db_session.execute(text("SELECT COUNT(*) c FROM usage_meter_definitions"))).scalar()

    r2 = await seed_meters(db_session)
    assert r2["meters"] == "skipped"
    count2 = (await db_session.execute(text("SELECT COUNT(*) c FROM usage_meter_definitions"))).scalar()

    assert count1 == count2 == 6


@pytest.mark.asyncio
async def test_system_owner_seed_idempotent(db_session):
    """Seed system_owner twice — only one created."""
    # Seed plans first (system_owner seed doesn't need it but migration does)
    await seed_plans(db_session)

    r1 = await seed_system_owner(db_session)
    assert r1["system_owner"] == "created"
    count1 = (await db_session.execute(
        text("SELECT COUNT(*) c FROM users WHERE platform_role = 'system_owner'")
    )).scalar()

    r2 = await seed_system_owner(db_session)
    assert r2["system_owner"] == "exists"
    count2 = (await db_session.execute(
        text("SELECT COUNT(*) c FROM users WHERE platform_role = 'system_owner'")
    )).scalar()

    assert count1 == count2 == 1


@pytest.mark.asyncio
async def test_full_seed_run_idempotent(db_session):
    """Running all seeds twice produces no duplicate data."""
    r1 = await run_all_saas_seeds(db_session)

    plan_count_1 = (await db_session.execute(text("SELECT COUNT(*) c FROM plan_definitions"))).scalar()
    meter_count_1 = (await db_session.execute(text("SELECT COUNT(*) c FROM usage_meter_definitions"))).scalar()
    owner_count_1 = (await db_session.execute(
        text("SELECT COUNT(*) c FROM users WHERE platform_role = 'system_owner'")
    )).scalar()

    r2 = await run_all_saas_seeds(db_session)

    plan_count_2 = (await db_session.execute(text("SELECT COUNT(*) c FROM plan_definitions"))).scalar()
    meter_count_2 = (await db_session.execute(text("SELECT COUNT(*) c FROM usage_meter_definitions"))).scalar()
    owner_count_2 = (await db_session.execute(
        text("SELECT COUNT(*) c FROM users WHERE platform_role = 'system_owner'")
    )).scalar()

    assert plan_count_1 == plan_count_2 == 3
    assert meter_count_1 == meter_count_2 == 6
    assert owner_count_1 == owner_count_2 == 1
    assert r2["plans"]["plans"] == "skipped"
    assert r2["meters"]["meters"] == "skipped"
    assert r2["system_owner"]["system_owner"] == "exists"


@pytest.mark.asyncio
async def test_migrate_existing_orgs_idempotent(db_session):
    """Migration creates subscriptions for orgs, is idempotent on re-run."""
    from src.models.organization import Organization
    from sqlalchemy import select

    await seed_plans(db_session)

    # Create an org without subscription
    org = Organization(name="MigTestOrg")
    db_session.add(org)
    await db_session.commit()

    # First migration
    r1 = await migrate_existing_orgs(db_session)
    sub_count_1 = (await db_session.execute(
        text("SELECT COUNT(*) c FROM org_subscriptions WHERE organization_id = :oid"),
        {"oid": org.id}
    )).scalar()
    assert sub_count_1 >= 1

    # Second migration — should skip already-subscribed orgs
    r2 = await migrate_existing_orgs(db_session)
    sub_count_2 = (await db_session.execute(
        text("SELECT COUNT(*) c FROM org_subscriptions WHERE organization_id = :oid"),
        {"oid": org.id}
    )).scalar()
    assert sub_count_2 == sub_count_1  # No duplicates


@pytest.mark.asyncio
async def test_slug_backfill_preserves_existing(db_session):
    """Migration backfills slugs without overwriting existing ones."""
    # Direct insert for id-based slug
    await db_session.execute(
        text("INSERT INTO organizations (id, name, slug, plan, is_active, created_at, updated_at) "
             "VALUES (gen_random_uuid(), 'SlugOrg', 'my-custom-slug', 'free', true, now(), now())")
    )
    await db_session.commit()

    await seed_plans(db_session)
    await migrate_existing_orgs(db_session)

    org = (await db_session.execute(
        text("SELECT slug FROM organizations WHERE name = 'SlugOrg'")
    )).fetchone()
    assert org.slug == "my-custom-slug"  # Not overwritten
