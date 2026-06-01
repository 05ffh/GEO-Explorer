"""P2-5 SaaS seed data — PlanDefinitions, UsageMeters, default System Owner."""
import logging
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

PLAN_SEEDS = [
    {
        "name": "free", "display_name": "Free", "tier": 0, "version": "1.0",
        "is_public": True, "is_deprecated": False, "is_active": True,
        "max_brands": 1, "max_users": 1, "max_competitors": 0,
        "max_api_keys": 0, "max_cms_targets": 0, "max_webhook_targets": 0,
        "max_reports_per_month": 0, "max_exports_per_month": 0,
        "max_collection_runs_per_month": 0, "max_questions_per_collection": 3,
        "max_platforms_per_collection": 2, "max_api_requests_per_month": 0,
        "data_retention_days": 90, "trend_history_days": 0, "max_storage_mb": 50,
        "features_json": {
            "feature_kpi_dashboard": True,
            "feature_reports_online": True,
        },
        "monthly_price_cny": 0, "yearly_price_cny": 0,
    },
    {
        "name": "pro", "display_name": "专业版", "tier": 1, "version": "1.0",
        "is_public": True, "is_deprecated": False, "is_active": True,
        "max_brands": 10, "max_users": 5, "max_competitors": 3,
        "max_api_keys": 3, "max_cms_targets": 3, "max_webhook_targets": 5,
        "max_reports_per_month": 20, "max_exports_per_month": 10,
        "max_collection_runs_per_month": 4, "max_questions_per_collection": 10,
        "max_platforms_per_collection": 3, "max_api_requests_per_month": 0,
        "data_retention_days": 365, "trend_history_days": 30, "max_storage_mb": 500,
        "features_json": {
            "feature_kpi_dashboard": True,
            "feature_benchmark": True, "feature_trends": True,
            "feature_reports_online": True, "feature_reports_pdf": True,
            "feature_reports_docx": True,
            "feature_cms_webhook": True,
            "feature_content_packages": True,
            "feature_data_export": True,
            "feature_team_members": True,
            "feature_cost_dashboard": True,
        },
        "monthly_price_cny": 999, "yearly_price_cny": 9590,
    },
    {
        "name": "enterprise", "display_name": "企业版", "tier": 2, "version": "1.0",
        "is_public": True, "is_deprecated": False, "is_active": True,
        "max_brands": -1, "max_users": -1, "max_competitors": -1,
        "max_api_keys": 10, "max_cms_targets": -1, "max_webhook_targets": -1,
        "max_reports_per_month": -1, "max_exports_per_month": -1,
        "max_collection_runs_per_month": -1, "max_questions_per_collection": 20,
        "max_platforms_per_collection": 5, "max_api_requests_per_month": 100000,
        "data_retention_days": -1, "trend_history_days": -1, "max_storage_mb": -1,
        "features_json": {
            "feature_kpi_dashboard": True,
            "feature_benchmark": True, "feature_trends": True,
            "feature_reports_online": True, "feature_reports_pdf": True,
            "feature_reports_docx": True, "feature_reports_branding": True,
            "feature_cms_webhook": True, "feature_cms_wordpress": True,
            "feature_api_access": True, "feature_api_write": True,
            "feature_content_packages": True,
            "feature_data_export": True,
            "feature_team_members": True,
            "feature_cost_dashboard": True,
        },
        "monthly_price_cny": None, "yearly_price_cny": None,
    },
]

METER_SEEDS = [
    {"meter_key": "collection_runs_per_month", "version": "1.0", "reset_period": "monthly",
     "is_billable": True, "is_customer_visible": True,
     "counting_rule_json": {"description": "进入 running 状态的采集任务计 1", "excludes_failed": True}},
    {"meter_key": "api_requests_per_month", "version": "1.0", "reset_period": "monthly",
     "is_billable": True, "is_customer_visible": True,
     "counting_rule_json": {"description": "非 health-check API 请求计 1，含 4xx，不含 5xx 重试"}},
    {"meter_key": "reports_per_month", "version": "1.0", "reset_period": "monthly",
     "is_billable": True, "is_customer_visible": True,
     "counting_rule_json": {"description": "成功生成的 ReportArtifact 计 1"}},
    {"meter_key": "exports_per_month", "version": "1.0", "reset_period": "monthly",
     "is_billable": False, "is_customer_visible": True,
     "counting_rule_json": {"description": "成功生成 DataExport 文件计 1"}},
    {"meter_key": "token_usage", "version": "1.0", "reset_period": "monthly",
     "is_billable": True, "is_customer_visible": False,
     "counting_rule_json": {"description": "input_tokens + output_tokens"}},
    {"meter_key": "storage_mb", "version": "1.0", "reset_period": "monthly",
     "is_billable": False, "is_customer_visible": True,
     "counting_rule_json": {"description": "当前未过期文件总大小（MB）"}},
]


async def seed_plans(db: AsyncSession) -> dict:
    """Seed PlanDefinitions. Skips existing."""
    from src.models.saas import PlanDefinition

    existing = (await db.execute(text("SELECT COUNT(*) c FROM plan_definitions"))).scalar()
    if existing:
        return {"plans": "skipped", "count": existing}

    for plan in PLAN_SEEDS:
        db.add(PlanDefinition(
            name=plan["name"], display_name=plan["display_name"],
            tier=plan["tier"], version=plan["version"],
            is_public=plan["is_public"], is_deprecated=plan["is_deprecated"],
            is_active=plan["is_active"],
            max_brands=plan["max_brands"], max_users=plan["max_users"],
            max_competitors=plan["max_competitors"], max_api_keys=plan["max_api_keys"],
            max_cms_targets=plan["max_cms_targets"], max_webhook_targets=plan["max_webhook_targets"],
            max_reports_per_month=plan["max_reports_per_month"],
            max_exports_per_month=plan["max_exports_per_month"],
            max_collection_runs_per_month=plan["max_collection_runs_per_month"],
            max_questions_per_collection=plan["max_questions_per_collection"],
            max_platforms_per_collection=plan["max_platforms_per_collection"],
            max_api_requests_per_month=plan["max_api_requests_per_month"],
            data_retention_days=plan["data_retention_days"],
            trend_history_days=plan["trend_history_days"],
            max_storage_mb=plan["max_storage_mb"],
            features_json=plan["features_json"],
            monthly_price_cny=plan["monthly_price_cny"],
            yearly_price_cny=plan["yearly_price_cny"],
        ))

    await db.commit()
    return {"plans": "seeded", "count": len(PLAN_SEEDS)}


async def seed_meters(db: AsyncSession) -> dict:
    """Seed UsageMeterDefinitions."""
    from src.models.saas import UsageMeterDefinition

    existing = (await db.execute(text("SELECT COUNT(*) c FROM usage_meter_definitions"))).scalar()
    if existing:
        return {"meters": "skipped", "count": existing}

    for m in METER_SEEDS:
        db.add(UsageMeterDefinition(
            meter_key=m["meter_key"], version=m["version"],
            counting_rule_json=m["counting_rule_json"],
            reset_period=m["reset_period"],
            is_billable=m["is_billable"], is_customer_visible=m["is_customer_visible"],
            description=m["counting_rule_json"].get("description", ""),
        ))

    await db.commit()
    return {"meters": "seeded", "count": len(METER_SEEDS)}


async def seed_system_owner(db: AsyncSession, email: str = "admin@geoexplorer.local",
                             password_hash: str = "") -> dict:
    """Create initial system_owner if none exists."""
    from src.models.organization import Organization
    from src.models.user import User
    from src.models.saas import PlatformAdminProfile

    existing = (await db.execute(
        text("SELECT COUNT(*) c FROM users WHERE platform_role = 'system_owner'")
    )).scalar()
    if existing:
        return {"system_owner": "exists", "count": existing}

    import hashlib
    if not password_hash:
        password_hash = hashlib.sha256("admin123".encode()).hexdigest()

    # Create org for the system owner
    org = Organization(name="GEO Platform", plan="enterprise", slug="geo-platform")
    db.add(org)
    await db.flush()

    # Create system_owner user
    user = User(
        organization_id=org.id, email=email, name="System Owner",
        role="owner", platform_role="system_owner",
        platform_mfa_required=True, password_hash=password_hash,
    )
    db.add(user)
    await db.flush()

    # Create PlatformAdminProfile
    db.add(PlatformAdminProfile(
        user_id=user.id, platform_role="system_owner", status="active",
        mfa_enforced=True, granted_by=user.id,
    ))

    await db.commit()
    return {"system_owner": "created", "email": email}


async def migrate_existing_orgs(db: AsyncSession) -> dict:
    """Migrate existing Organization.plan to OrgSubscription."""
    from src.models.saas import PlanDefinition, OrgSubscription
    from src.models.organization import Organization
    from sqlalchemy import select as sa_select, exists as sa_exists

    # Find the free plan
    free_plan = (await db.execute(
        sa_select(PlanDefinition).where(
            PlanDefinition.name == "free", PlanDefinition.is_active == True
        ).limit(1)
    )).scalar_one_or_none()
    if not free_plan:
        return {"migration": "skipped", "reason": "no plans found"}

    # Create slugs for orgs without one
    await db.execute(text("""
        UPDATE organizations SET slug = 'org-' || replace(id::text, '-', '')::varchar(12)
        WHERE slug IS NULL
    """))

    # Find orgs without an active subscription
    subq = sa_exists().where(
        OrgSubscription.organization_id == Organization.id,
        OrgSubscription.status.in_(['active', 'trialing', 'grace', 'past_due', 'internal_test']),
    )
    orgs_without_sub = (await db.execute(
        sa_select(Organization).where(~subq)
    )).scalars().all()

    migrated = 0
    for org in orgs_without_sub:
        plan_name = (org.plan or "free") if hasattr(org, 'plan') else "free"
        target_plan = free_plan
        if plan_name != "free":
            p = (await db.execute(
                sa_select(PlanDefinition).where(
                    PlanDefinition.name == plan_name, PlanDefinition.is_active == True
                ).limit(1)
            )).scalar_one_or_none()
            if p:
                target_plan = p

        db.add(OrgSubscription(
            organization_id=org.id, plan_id=target_plan.id,
            plan_version=target_plan.version, status="active",
        ))
        migrated += 1

    await db.commit()
    return {"migration": "completed", "migrated_orgs": migrated}


async def run_all_saas_seeds(db: AsyncSession, system_owner_email: str = "admin@geoexplorer.local") -> dict:
    """Run all SaaS seed operations."""
    plans = await seed_plans(db)
    meters = await seed_meters(db)
    migration = await migrate_existing_orgs(db)
    sys_owner = await seed_system_owner(db, email=system_owner_email)
    return {"plans": plans, "meters": meters, "migration": migration, "system_owner": sys_owner}
