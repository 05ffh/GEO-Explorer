"""Collector engine tests — updated for adapter_registry dependency injection."""
import pytest
from sqlalchemy import select
from src.collector.engine import run_collection
from src.adapters.mock import MockPlatformAdapter
from src.models.organization import Organization
from src.models.user import User
from src.models.brand import Brand
from src.models.ground_truth import GroundTruthVersion
from src.models.query_template import QueryTemplate
from src.models.prompt_version import PromptVersion
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.models.api_usage import ApiUsage

PLATFORMS_2 = ["deepseek", "kimi"]


def _mock_registry_2(platforms=None, **modes):
    """Build a mock registry for specified platforms."""
    reg = {}
    for p in (platforms or PLATFORMS_2):
        mode = modes.get(p, "success")
        reg[p] = lambda p=p, m=mode: MockPlatformAdapter(p, m, latency_range=(5, 10))
    return reg


@pytest.mark.asyncio
async def test_collection_creates_full_lineage(db_session, monkeypatch):
    org = Organization(name="CollectorTest")
    db_session.add(org); await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand); await db_session.commit()
    gt = GroundTruthVersion(brand_id=brand.id, version=1,
        ground_truth_json={"official_name": "TestBrand", "industry": "Tech"}, status="active")
    db_session.add(gt)
    prompt = PromptVersion(name="test-prompt", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt)
    tmpl = QueryTemplate(organization_id=org.id, dimension="定义认知",
        template_text="{品牌} 是什么？", priority=1, is_active=True, status="active")
    db_session.add(tmpl); await db_session.commit()

    registry = _mock_registry_2()
    monkeypatch.setattr("src.collector.engine.PLATFORMS", PLATFORMS_2)
    run = await run_collection(brand.id, org.id, db_session, trigger_type="manual",
                               adapter_registry=registry)
    await db_session.refresh(run)

    assert run.collection_status == "completed"
    assert run.total_queries == 2
    assert run.success_count == 2
    qrs = (await db_session.execute(
        select(QueryResult).where(QueryResult.collection_run_id == run.id)
    )).scalars().all()
    assert len(qrs) == 2
    for qr in qrs:
        assert qr.status == "success"
    usages = (await db_session.execute(
        select(ApiUsage).where(ApiUsage.collection_run_id == run.id)
    )).scalars().all()
    assert len(usages) == 2


@pytest.mark.asyncio
async def test_kimi_429_retry(db_session, monkeypatch):
    org = Organization(name="RetryTest")
    db_session.add(org); await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand); await db_session.flush()
    gt = GroundTruthVersion(brand_id=brand.id, version=1,
        ground_truth_json={"name": "TestBrand"}, status="active")
    db_session.add(gt)
    tmpl = QueryTemplate(organization_id=org.id, dimension="定义认知",
        template_text="{品牌} 是什么？", priority=1, is_active=True, status="active")
    db_session.add(tmpl)
    prompt = PromptVersion(name="test", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt); await db_session.commit()

    # Build a registry with a retry-counting mock for kimi
    call_count = [0]
    class RetryMock(MockPlatformAdapter):
        async def query(self, prompt, system_prompt="", **kwargs):
            call_count[0] += 1
            if call_count[0] <= 1:
                from src.adapters.base import AIResponse
                return AIResponse(platform=self.platform_name, question=prompt,
                    answer_text="", latency_ms=100,
                    error="Error code: 429", error_code="platform_rate_limited",
                    error_message="rate limit", retryable=True)
            return await super().query(prompt, system_prompt, **kwargs)

    registry = {"kimi": lambda: RetryMock("kimi", "success", latency_range=(5, 10))}
    # Re-enable retries for this specific test
    import src.config as _cfg
    _cfg.settings.platform_rate_limits["kimi"]["max_retries"] = 1
    _cfg.settings.platform_rate_limits["kimi"]["backoff_base_seconds"] = 1

    monkeypatch.setattr("src.collector.engine.PLATFORMS", ["kimi"])
    run = await run_collection(brand.id, org.id, db_session, trigger_type="manual",
                               auto_analyze=False, adapter_registry=registry)
    await db_session.refresh(run)

    assert run.collection_status == "completed"
    assert run.success_count == 1
    qr = (await db_session.execute(
        select(QueryResult).where(QueryResult.collection_run_id == run.id)
    )).scalars().first()
    assert qr.retry_count >= 1
    assert qr.rate_limited is True
    assert qr.status == "success"


@pytest.mark.asyncio
async def test_template_health_blocks_collection_when_invalid_ratio_exceeds_threshold(db_session, monkeypatch):
    org = Organization(name="HealthBlockTest")
    db_session.add(org); await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand); await db_session.commit()
    gt = GroundTruthVersion(brand_id=brand.id, version=1,
        ground_truth_json={"official_name": "TestBrand", "industry": "Tech"}, status="active")
    db_session.add(gt)
    prompt = PromptVersion(name="test-prompt", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt)
    valid_tmpl = QueryTemplate(organization_id=org.id, dimension="定义认知",
        template_text="{品牌} 是什么？", priority=1, is_active=True, status="active")
    invalid_tmpl1 = QueryTemplate(organization_id=org.id, dimension="竞品对比",
        template_text="{品牌} 和 {竞品} 有什么区别？", priority=1, is_active=True,
        question_type="brand_comparison", status="active")
    invalid_tmpl2 = QueryTemplate(organization_id=org.id, dimension="用户场景",
        template_text="{目标用户} 适合什么平台？", priority=1, is_active=True,
        question_type="user_recommendation", status="active")
    db_session.add_all([valid_tmpl, invalid_tmpl1, invalid_tmpl2]); await db_session.commit()

    registry = _mock_registry_2(["deepseek"], deepseek="timeout")
    monkeypatch.setattr("src.collector.engine.PLATFORMS", ["deepseek"])
    run = await run_collection(brand.id, org.id, db_session, trigger_type="manual",
                               adapter_registry=registry)
    await db_session.refresh(run)

    assert run.collection_status == "failed"
    health = run.template_health_report_json
    assert health is not None
    assert health["invalid_ratio"] > 0.20
    assert health["can_collect"] is False


@pytest.mark.asyncio
async def test_template_health_allows_collection_when_invalid_ratio_below_threshold(db_session, monkeypatch):
    org = Organization(name="HealthPassTest")
    db_session.add(org); await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", aliases=["TB"], industry="Tech")
    db_session.add(brand); await db_session.commit()
    gt = GroundTruthVersion(brand_id=brand.id, version=1,
        ground_truth_json={"official_name": "TestBrand", "industry": "Tech"}, status="active")
    db_session.add(gt)
    prompt = PromptVersion(name="test-prompt", system_prompt="Be honest.", version=1, status="active")
    db_session.add(prompt)
    tmpl1 = QueryTemplate(organization_id=org.id, dimension="定义认知",
        template_text="{品牌} 是什么？", priority=1, is_active=True, status="active")
    tmpl2 = QueryTemplate(organization_id=org.id, dimension="行业属性",
        template_text="{品牌} 属于什么行业？", priority=1, is_active=True,
        question_type="brand_attribute", status="active")
    db_session.add_all([tmpl1, tmpl2]); await db_session.commit()

    registry = _mock_registry_2(["deepseek"], deepseek="success")
    monkeypatch.setattr("src.collector.engine.PLATFORMS", ["deepseek"])
    run = await run_collection(brand.id, org.id, db_session, trigger_type="manual",
                               adapter_registry=registry)
    await db_session.refresh(run)

    assert run.collection_status == "completed"
    health = run.template_health_report_json
    assert health is not None
    assert health["can_collect"] is True
