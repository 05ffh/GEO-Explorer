import pytest


@pytest.mark.asyncio
async def test_collect_gt_creates_candidate(db_session, monkeypatch):
    from src.models.organization import Organization
    from src.models.brand import Brand

    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="象往科技", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    from src.collector import gt_collector as gc

    async def mock_collect_from_ai(*a, **kw):
        return []

    async def mock_collect_from_search(*a, **kw):
        return []

    monkeypatch.setattr(gc, "_collect_from_ai_platforms", mock_collect_from_ai)
    monkeypatch.setattr(gc, "_collect_from_search", mock_collect_from_search)

    candidate = await gc.collect_gt_candidate(str(brand.id), str(org.id), db_session)
    assert candidate is not None
    assert candidate.status == "pending_review"


@pytest.mark.asyncio
async def test_collect_gt_brand_not_found(db_session):
    from src.collector.gt_collector import collect_gt_candidate

    with pytest.raises(ValueError, match="Brand not found"):
        await collect_gt_candidate("00000000-0000-0000-0000-000000000000", "00000000-0000-0000-0000-000000000000", db_session)
