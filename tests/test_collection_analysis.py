import pytest
from sqlalchemy import select
from src.models.organization import Organization
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion
from src.models.query_template import QueryTemplate
from src.models.prompt_version import PromptVersion
from src.models.collection_run import CollectionRun
from src.analyzer.collection_analysis import should_analyze, run_analysis_for_collection


@pytest.mark.asyncio
async def test_should_analyze_sufficient_data(db_session):
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.flush()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="partial", total_queries=20,
        success_count=12, failure_count=8,
    )
    db_session.add(run)
    await db_session.commit()

    assert should_analyze(run, success_platform_count=3) is True


@pytest.mark.asyncio
async def test_should_analyze_insufficient_data(db_session):
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="partial", total_queries=10,
        success_count=3, failure_count=7,
    )
    db_session.add(run)
    await db_session.commit()
    assert should_analyze(run, success_platform_count=1) is False


@pytest.mark.asyncio
async def test_should_analyze_failed_collection(db_session):
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="failed", total_queries=22,
        success_count=0, failure_count=22,
    )
    db_session.add(run)
    await db_session.commit()
    assert should_analyze(run, success_platform_count=0) is False


@pytest.mark.asyncio
async def test_analysis_skipped_when_below_threshold(db_session):
    """数据不足时 analysis_status=skipped，不生成 MetricsSnapshot."""
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="partial", total_queries=5,
        success_count=2, failure_count=3,
    )
    db_session.add(run)
    await db_session.commit()

    await run_analysis_for_collection(run.id, org.id, db_session)
    await db_session.refresh(run)
    assert run.analysis_status == "skipped"


@pytest.mark.asyncio
async def test_analysis_not_duplicated_on_rerun(db_session):
    """同一个 collection_run 重试时不重复生成 MetricsSnapshot."""
    from src.collector import engine as collector_engine
    from src.adapters.mock import MockPlatformAdapter

    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand)
    await db_session.flush()

    gt = GroundTruthVersion(brand_id=brand.id, version=1, ground_truth_json={"name": "TestBrand"}, status="active")
    db_session.add(gt)
    tmpl = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    db_session.add(tmpl)
    prompt = PromptVersion(name="test", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt)
    await db_session.commit()

    # Use adapter_registry injection instead of monkeypatch
    def _make_adapter(p):
        return MockPlatformAdapter(p, "success", latency_range=(5, 20))
    registry = {p: lambda p=p: _make_adapter(p) for p in ["deepseek", "kimi"]}

    # Override analysis threshold so 2 queries suffice
    from src.config import settings
    old_min_queries = settings.min_success_queries_for_analysis
    old_min_platforms = settings.min_success_platforms_for_analysis
    settings.min_success_queries_for_analysis = 2
    settings.min_success_platforms_for_analysis = 2

    try:
        run = await collector_engine.run_collection(
            brand.id, org.id, db_session, trigger_type="manual",
            auto_analyze=True, adapter_registry=registry,
        )
    finally:
        settings.min_success_queries_for_analysis = old_min_queries
        settings.min_success_platforms_for_analysis = old_min_platforms

    await db_session.refresh(run)
    assert run.analysis_status == "completed"

    from src.models.metrics_snapshot import MetricsSnapshot
    snapshots = (await db_session.execute(
        select(MetricsSnapshot).where(MetricsSnapshot.collection_run_id == run.id)
    )).scalars().all()
    assert len(snapshots) == 1

    # 手动重跑分析，不应重复创建 MetricsSnapshot
    await run_analysis_for_collection(run.id, org.id, db_session)
    snapshots_after = (await db_session.execute(
        select(MetricsSnapshot).where(MetricsSnapshot.collection_run_id == run.id)
    )).scalars().all()
    assert len(snapshots_after) == 1
