import pytest
from sqlalchemy import select
from src.collector.engine import run_collection
from src.models.organization import Organization
from src.models.user import User
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion
from src.models.query_template import QueryTemplate
from src.models.prompt_version import PromptVersion
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.models.api_usage import ApiUsage


@pytest.mark.asyncio
async def test_collection_creates_full_lineage(db_session, monkeypatch):
    # Seed org, brand, GT, templates, prompt
    org = Organization(name="CollectorTest")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    gt = GroundTruthVersion(
        brand_id=brand.id, version=1,
        ground_truth_json={"official_name": "TestBrand", "industry": "Tech"},
        status="active",
    )
    db_session.add(gt)

    prompt = PromptVersion(name="test-prompt", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt)

    tmpl = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    db_session.add(tmpl)
    await db_session.commit()

    # Replace adapters with MockAdapter
    from src.collector import engine as collector_engine
    from src.adapters.mock import MockAdapter

    def mock_get_adapter(platform_name):
        return MockAdapter(platform_name=platform_name)

    monkeypatch.setattr(collector_engine, "get_adapter", mock_get_adapter)
    monkeypatch.setattr(collector_engine, "PLATFORMS", ["deepseek", "kimi"])

    # Run collection
    run = await run_collection(brand.id, org.id, db_session, trigger_type="manual")
    await db_session.refresh(run)

    # Verify CollectionRun
    assert run.collection_status == "completed"
    assert run.total_queries == 2  # 2 platforms × 1 template
    assert run.success_count == 2
    assert run.failure_count == 0
    assert run.success_count + run.failure_count == run.total_queries

    # Verify QueryResults linked to CollectionRun
    qrs = (await db_session.execute(
        select(QueryResult).where(QueryResult.collection_run_id == run.id)
    )).scalars().all()
    assert len(qrs) == 2
    for qr in qrs:
        assert qr.collection_run_id == run.id
        assert qr.status == "success"

    # Verify ApiUsage linked to QueryResult and CollectionRun
    usages = (await db_session.execute(
        select(ApiUsage).where(ApiUsage.collection_run_id == run.id)
    )).scalars().all()
    assert len(usages) == 2
    for usage in usages:
        assert usage.collection_run_id == run.id
        assert usage.query_result_id in {qr.id for qr in qrs}


@pytest.mark.asyncio
async def test_kimi_429_retry(db_session, monkeypatch):
    """Kimi 返回 429 → 重试后成功，记录 retry_count."""
    org = Organization(name="RetryTest")
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

    from src.collector import engine as collector_engine
    from src.adapters.mock import MockAdapter

    call_count = [0]

    class RetryMockAdapter(MockAdapter):
        async def query(self, prompt, system_prompt="", **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                from src.adapters.base import AIResponse
                return AIResponse(
                    platform=self.platform_name, question=prompt, answer_text="",
                    latency_ms=100, error="Error code: 429 - {'error': {'message': 'rate limit'}}",
                )
            return await super().query(prompt, system_prompt, **kwargs)

    monkeypatch.setattr(collector_engine, "get_adapter", lambda p: RetryMockAdapter(platform_name=p))
    monkeypatch.setattr(collector_engine, "PLATFORMS", ["kimi"])

    run = await collector_engine.run_collection(brand.id, org.id, db_session, trigger_type="manual", auto_analyze=False)
    await db_session.refresh(run)

    assert run.collection_status == "completed"
    assert run.success_count == 1
    qr = (await db_session.execute(
        select(QueryResult).where(QueryResult.collection_run_id == run.id)
    )).scalars().first()
    assert qr.retry_count >= 2
    assert qr.rate_limited is True
    assert qr.status == "success"


@pytest.mark.asyncio
async def test_template_health_blocks_collection_when_invalid_ratio_exceeds_threshold(
    db_session, monkeypatch,
):
    """P0-8: invalid_ratio > 20% → collection blocked, status=failed."""
    org = Organization(name="HealthBlockTest")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    gt = GroundTruthVersion(
        brand_id=brand.id, version=1,
        ground_truth_json={"official_name": "TestBrand", "industry": "Tech"},
        status="active",
    )
    db_session.add(gt)

    prompt = PromptVersion(name="test-prompt", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt)

    # 1 valid + 2 invalid = 2/3 = 66.7% > 20% threshold
    valid_tmpl = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    invalid_tmpl1 = QueryTemplate(
        dimension="竞品对比", template_text="{品牌} 和 {竞品} 有什么区别？",
        priority=1, is_active=True, question_type="brand_comparison",
    )
    invalid_tmpl2 = QueryTemplate(
        dimension="用户场景", template_text="{目标用户} 适合什么平台？",
        priority=1, is_active=True, question_type="user_recommendation",
    )
    db_session.add_all([valid_tmpl, invalid_tmpl1, invalid_tmpl2])
    await db_session.commit()

    from src.collector import engine as collector_engine
    from src.adapters.mock import MockAdapter

    monkeypatch.setattr(collector_engine, "get_adapter", lambda p: MockAdapter(platform_name=p))
    monkeypatch.setattr(collector_engine, "PLATFORMS", ["deepseek"])

    run = await run_collection(brand.id, org.id, db_session, trigger_type="manual")
    await db_session.refresh(run)

    assert run.collection_status == "failed"
    err = run.collection_error_summary or {}
    assert err.get("reason") == "template_health_threshold"
    assert err.get("invalid_ratio", 0) > 0.20
    # Verify health report was still saved
    health = run.template_health_report_json
    assert health is not None
    assert health["can_collect"] is False
    assert health["invalid_ratio"] > 0.20
    # Verify no queries were executed
    assert run.success_count == 0


@pytest.mark.asyncio
async def test_template_health_allows_collection_when_invalid_ratio_below_threshold(
    db_session, monkeypatch,
):
    """P0-8: invalid_ratio <= 20% → collection proceeds normally."""
    org = Organization(name="HealthPassTest")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    gt = GroundTruthVersion(
        brand_id=brand.id, version=1,
        ground_truth_json={"official_name": "TestBrand", "industry": "Tech"},
        status="active",
    )
    db_session.add(gt)

    prompt = PromptVersion(name="test-prompt", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt)

    # All valid templates → 0% invalid ≤ 20%
    tmpl1 = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    tmpl2 = QueryTemplate(
        dimension="行业属性", template_text="{品牌} 属于什么行业？",
        priority=1, is_active=True, question_type="brand_attribute",
    )
    db_session.add_all([tmpl1, tmpl2])
    await db_session.commit()

    from src.collector import engine as collector_engine
    from src.adapters.mock import MockAdapter

    monkeypatch.setattr(collector_engine, "get_adapter", lambda p: MockAdapter(platform_name=p))
    monkeypatch.setattr(collector_engine, "PLATFORMS", ["deepseek"])

    run = await run_collection(brand.id, org.id, db_session, trigger_type="manual")
    await db_session.refresh(run)

    assert run.collection_status == "completed"
    health = run.template_health_report_json
    assert health is not None
    assert health["can_collect"] is True
    assert health["invalid_ratio"] <= 0.20
