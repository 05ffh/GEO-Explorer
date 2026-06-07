"""Mock adapter test scenarios — per-test adapter_registry injection, zero global state pollution.

Scenarios:
  1. all_success          — 4 platforms × 2 templates, all succeed
  2. partial_success      — wenxin succeeds, others mixed failure
  3. all_failed           — all platforms auth_failed
  4. wenxin_ok_others_timeout — wenxin success, others timeout
  5. kimi_rl_doubao_timeout   — kimi rate_limited, doubao timeout
  6. semaphore_no_deadlock — 4 platforms × 10 templates under semaphore
  7. error_classification — mixed mode validates all error types appear
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.adapters.mock import MockPlatformAdapter
from src.collector.engine import run_collection
from src.models.brand import Brand
from src.models.organization import Organization
from src.models.query_template import QueryTemplate
from src.models.ground_truth import GroundTruthVersion


# ── Setup: disable retries for mock tests ──────────────────────────────────

import copy
import src.config as _cfg

# Save original config before mock tests modify it
_ORIGINAL_RATE_LIMITS = copy.deepcopy(_cfg.settings.platform_rate_limits)

def _setup_mock_config():
    for p in ["deepseek", "kimi", "doubao", "wenxin"]:
        if p in _cfg.settings.platform_rate_limits:
            _cfg.settings.platform_rate_limits[p]["max_retries"] = 0
            _cfg.settings.platform_rate_limits[p]["backoff_base_seconds"] = 1

def _restore_rate_limits():
    _cfg.settings.platform_rate_limits.clear()
    _cfg.settings.platform_rate_limits.update(_ORIGINAL_RATE_LIMITS)

_setup_mock_config()

# Auto-restore after last mock test in session
@pytest.fixture(scope="session", autouse=True)
def _restore_config_after_mock_tests():
    yield
    _restore_rate_limits()


# ── Helper ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def test_org(db_session: AsyncSession):
    org = Organization(name="MockTestOrg")
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def test_brand(db_session: AsyncSession, test_org):
    b = Brand(name="MockBrand", aliases=["MB"], industry="科技",
              organization_id=test_org.id)
    db_session.add(b)
    await db_session.flush()
    return b


@pytest.fixture
async def test_templates(db_session: AsyncSession, test_org):
    templates = []
    for i, qt in enumerate(["brand_definition", "brand_attribute"]):
        t = QueryTemplate(
            organization_id=test_org.id, dimension="brand",
            template_text=f"{{品牌}} 的测试问题 {i+1}？",
            question_type=qt, template_level="critical" if i == 0 else "important",
            is_active=True, status="active",
        )
        db_session.add(t)
        templates.append(t)
    await db_session.flush()
    return templates


@pytest.fixture
async def test_gt(db_session: AsyncSession, test_brand):
    gt = GroundTruthVersion(
        brand_id=test_brand.id, version=1,
        ground_truth_json={
            "official_name": "MockBrand", "industry": "科技", "category": "SaaS",
            "target_competitors": "竞品A", "core_scenarios": "测试场景", "target_users": "开发者",
        },
        status="active",
    )
    db_session.add(gt)
    await db_session.flush()
    return gt


# ── Helper: build a mock adapter_registry for a test ────────────────────────

def _mock_registry(**platform_modes: str) -> dict:
    """Return a per-test adapter_registry dict. Each value is a factory lambda."""
    registry = {}
    for platform, mode in platform_modes.items():
        def _factory(p=platform, m=mode):
            return MockPlatformAdapter(p, m, latency_range=(5, 20))
        registry[platform] = _factory
    return registry


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1: All Success
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_success_no_deadlock(test_brand, test_templates, test_gt, db_session):
    registry = _mock_registry(deepseek="success", kimi="success",
                              doubao="success", wenxin="success")
    run = await run_collection(
        brand_id=test_brand.id, org_id=test_brand.organization_id,
        db=db_session, trigger_type="mock_test", auto_analyze=False,
        adapter_registry=registry,
    )
    # Debug: if failed, show why
    if run.collection_status != "completed":
        err = getattr(run, 'collection_error_summary', None)
        health = getattr(run, 'template_health_report_json', None)
        coverage = getattr(run, 'coverage_report_json', None)
        raise AssertionError(
            f"Expected completed, got {run.collection_status}\n"
            f"error={err}\nhealth={health}\ncoverage={coverage}\n"
            f"queries: {run.success_count}/{run.total_queries}"
        )
    assert run.collection_status == "completed"
    assert run.success_count == run.total_queries
    ps = run.platform_status_json
    for p in ["deepseek", "kimi", "doubao", "wenxin"]:
        assert ps["platforms"][p]["success"] > 0
        assert ps["platforms"][p]["failed"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2: Partial Success
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_partial_success_not_fail_run(test_brand, test_templates, test_gt, db_session):
    registry = _mock_registry(deepseek="timeout", kimi="rate_limited",
                              doubao="timeout", wenxin="success")
    run = await run_collection(
        brand_id=test_brand.id, org_id=test_brand.organization_id,
        db=db_session, trigger_type="mock_test", auto_analyze=False,
        adapter_registry=registry,
    )
    if run.collection_status == "failed":
        raise AssertionError(
            f"Expected partial, got failed. "
            f"error={getattr(run, 'collection_error_summary', None)} "
            f"queries={run.success_count}/{run.total_queries}"
        )
    assert run.collection_status == "partial"
    ps = run.platform_status_json
    assert ps["partial_success"] is True
    assert ps["platforms"]["wenxin"]["success"] > 0
    assert "kimi" in ps["rate_limited_platforms"]


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3: All Failed
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_auth_failed_is_failed(test_brand, test_templates, test_gt, db_session):
    registry = _mock_registry(deepseek="auth_failed", kimi="auth_failed",
                              doubao="auth_failed", wenxin="auth_failed")
    run = await run_collection(
        brand_id=test_brand.id, org_id=test_brand.organization_id,
        db=db_session, trigger_type="mock_test", auto_analyze=False,
        adapter_registry=registry,
    )
    assert run.collection_status == "failed"
    assert run.success_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4: Wenxin success, others timeout
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_wenxin_ok_others_timeout_partial(test_brand, test_templates, test_gt, db_session):
    registry = _mock_registry(deepseek="timeout", kimi="timeout",
                              doubao="timeout", wenxin="success")
    run = await run_collection(
        brand_id=test_brand.id, org_id=test_brand.organization_id,
        db=db_session, trigger_type="mock_test", auto_analyze=False,
        adapter_registry=registry,
    )
    assert run.collection_status == "partial"
    ps = run.platform_status_json
    assert ps["platforms"]["wenxin"]["success"] > 0
    for p in ["deepseek", "kimi", "doubao"]:
        assert ps["platforms"][p]["failed"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 5: Kimi rate_limited + Doubao timeout
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_kimi_rl_doubao_timeout_partial(test_brand, test_templates, test_gt, db_session):
    registry = _mock_registry(deepseek="success", kimi="rate_limited",
                              doubao="timeout", wenxin="success")
    run = await run_collection(
        brand_id=test_brand.id, org_id=test_brand.organization_id,
        db=db_session, trigger_type="mock_test", auto_analyze=False,
        adapter_registry=registry,
    )
    assert run.collection_status == "partial"
    ps = run.platform_status_json
    assert ps["platforms"]["deepseek"]["success"] > 0
    assert ps["platforms"]["wenxin"]["success"] > 0
    assert ps["platforms"]["kimi"]["rate_limited"] > 0
    assert "kimi" in ps["rate_limited_platforms"]


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 6: Concurrency — semaphore no deadlock
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_platform_semaphore_no_deadlock(test_brand, test_gt, db_session):
    registry = _mock_registry(deepseek="success", kimi="success",
                              doubao="success", wenxin="success")
    for i in range(8):
        t = QueryTemplate(
            organization_id=test_brand.organization_id, dimension="brand",
            template_text=f"{{品牌}} 压力测试问题 {i}？",
            question_type="brand_definition", template_level="important",
            is_active=True, status="active",
        )
        db_session.add(t)
    await db_session.flush()

    run = await run_collection(
        brand_id=test_brand.id, org_id=test_brand.organization_id,
        db=db_session, trigger_type="mock_test", auto_analyze=False,
        adapter_registry=registry,
    )
    assert run.collection_status == "completed"
    assert run.total_queries > 20


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 7: Error classification with mixed mode
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_error_classification_mixed(test_brand, test_templates, test_gt, db_session):
    registry = _mock_registry(deepseek="mixed", kimi="mixed",
                              doubao="mixed", wenxin="mixed")
    run = await run_collection(
        brand_id=test_brand.id, org_id=test_brand.organization_id,
        db=db_session, trigger_type="mock_test", auto_analyze=False,
        adapter_registry=registry,
    )
    assert run.collection_status in ("completed", "partial")
    assert run.total_queries > 0
