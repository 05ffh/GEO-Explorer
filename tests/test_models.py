import pytest
from datetime import datetime, timezone
from src.models.organization import Organization
from src.models.user import User
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion
from src.models.query_template import QueryTemplate
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.models.api_usage import ApiUsage


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


@pytest.mark.asyncio
async def test_collection_lineage(db_session):
    org = Organization(name="LineageTest")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="LineageBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    run = CollectionRun(organization_id=org.id, brand_id=brand.id, trigger_type="manual",
                        total_queries=2, collection_status="completed")
    db_session.add(run)
    await db_session.commit()
    assert run.id is not None
    assert run.total_queries == 2

    tmpl = QueryTemplate(dimension="定义认知", template_text="什么是{品牌}？", priority=1)
    db_session.add(tmpl)
    await db_session.commit()

    qr = QueryResult(brand_id=brand.id, organization_id=org.id, collection_run_id=run.id,
                     platform="deepseek", template_id=tmpl.id, question="什么是LineageBrand？",
                     answer_text="LineageBrand is a tech company.", status="success",
                     collected_at=datetime.now(timezone.utc))
    db_session.add(qr)
    await db_session.commit()

    usage = ApiUsage(organization_id=org.id, brand_id=brand.id, collection_run_id=run.id,
                     platform="deepseek", query_result_id=qr.id,
                     prompt_tokens=10, completion_tokens=20, cost=0)
    db_session.add(usage)
    await db_session.commit()
    assert usage.query_result_id == qr.id
    assert usage.collection_run_id == run.id
