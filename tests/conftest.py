import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from src.config import settings
from src.models.base import Base

TRUNCATE_ALL = (
    "TRUNCATE TABLE action_themes, content_packages, gt_reviews, gt_evidences, gt_candidates, "
    "insight_summaries, hallucination_results, api_usage_logs, query_results, "
    "metrics_snapshots, action_plans, content_library, collection_runs, "
    "competitor_sets, ground_truth_versions, prompt_versions, query_templates, "
    "publish_attempts, publish_events, publish_requests, publish_batches, publish_targets, "
    "cms_field_mappings, publish_status_callbacks, "
    "report_delivery_attempts, report_download_events, report_download_links, "
    "report_artifacts, report_subscriptions, report_schedules, "
    "report_schedule_runs, report_batches, report_brandings, "
    "benchmark_snapshots, gap_attribution_results, benchmark_definitions, "
    "trend_insight_events, trend_insights, platform_trend_incidents, "
    "trend_analysis_definitions, model_events, impact_events, "
    "data_deletion_requests, data_exports, api_key_usage_logs, "
    "org_invites, org_subscriptions, api_keys, "
    "plan_change_requests, plan_definitions, usage_meter_definitions, "
    "usage_budgets, usage_events, usage_snapshots, "
    "feature_flag_overrides, feature_flags, emergency_pauses, "
    "platform_access_sessions, platform_admin_profiles, "
    "platform_approval_requests, cost_alerts, model_pricing, "
    "audit_logs, audit_integrity_checks, rate_limit_policies, "
    "queue_alerts, task_events, task_states, "
    "brands, users, organizations CASCADE"
)


@pytest_asyncio.fixture(scope="session")
async def engine():
    e = create_async_engine(settings.test_database_url, poolclass=NullPool)
    async with e.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    yield e
    await e.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    conn = await engine.connect()
    await conn.execute(text(TRUNCATE_ALL))
    await conn.commit()
    await conn.close()
