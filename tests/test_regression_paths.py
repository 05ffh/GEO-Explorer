"""Regression tests for diagnostic paths and brand validation (P0-4, P0-1)."""
import pytest
from sqlalchemy import select
from src.models.brand import Brand


class TestBrandValidation:
    """P0-4: Brand lookup must fail-fast for invalid brand_id or empty name."""

    @pytest.mark.asyncio
    async def test_nonexistent_brand_returns_none(self, db_session):
        """brand_id not in DB → query returns None (caller must exit)."""
        result = (
            await db_session.execute(
                select(Brand).where(Brand.id == "00000000-0000-0000-0000-000000000000")
            )
        ).scalar_one_or_none()
        assert result is None

    @pytest.mark.asyncio
    async def test_existing_brand_returns_brand(self, db_session):
        """Valid brand_id → brand returned with name."""
        from src.models.organization import Organization
        org = Organization(name="RegressionTest")
        db_session.add(org)
        await db_session.flush()
        brand = Brand(
            organization_id=org.id, name="TestBrand", industry="Tech"
        )
        db_session.add(brand)
        await db_session.commit()

        result = (
            await db_session.execute(
                select(Brand).where(Brand.id == brand.id)
            )
        ).scalar_one_or_none()
        assert result is not None
        assert result.name == "TestBrand"

    @pytest.mark.asyncio
    async def test_empty_brand_name_detected(self, db_session):
        """Brand with empty name → .name.strip() is falsy."""
        from src.models.organization import Organization
        org = Organization(name="EmptyNameTest")
        db_session.add(org)
        await db_session.flush()
        brand = Brand(
            organization_id=org.id, name="   ", industry="Tech"
        )
        db_session.add(brand)
        await db_session.commit()

        result = (
            await db_session.execute(
                select(Brand).where(Brand.id == brand.id)
            )
        ).scalar_one_or_none()
        assert result is not None
        assert not result.name.strip()
