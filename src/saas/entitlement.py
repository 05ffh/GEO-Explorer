"""Effective Entitlement resolver — 7-level priority + source_trace (P2-5)."""
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.saas import (OrgSubscription, PlanDefinition, FeatureFlag,
                               FeatureFlagOverride, EmergencyPause)

logger = logging.getLogger(__name__)

UNIFIED_FEATURE_KEYS = [
    "feature_kpi_dashboard", "feature_benchmark", "feature_trends",
    "feature_reports_online", "feature_reports_pdf", "feature_reports_docx",
    "feature_reports_branding", "feature_cms_webhook", "feature_cms_wordpress",
    "feature_api_access", "feature_api_write", "feature_content_packages",
    "feature_data_export", "feature_team_members", "feature_cost_dashboard",
]

DEFAULT_FREE_ENTITLEMENTS = {
    "features": {"feature_kpi_dashboard": True, "feature_reports_online": True},
    "limits": {"max_brands": 1, "max_users": 1, "max_competitors": 0,
               "max_api_keys": 0, "max_cms_targets": 0, "max_webhook_targets": 0,
               "max_reports_per_month": 0, "max_exports_per_month": 0,
               "max_collection_runs_per_month": 0, "data_retention_days": 90,
               "trend_history_days": 0, "max_storage_mb": 100},
    "formats": {"report_export": []},
}


async def get_active_subscription(org_id, db: AsyncSession):
    """Get the active OrgSubscription for an organization."""
    result = await db.execute(
        select(OrgSubscription).where(
            OrgSubscription.organization_id == org_id,
            OrgSubscription.status.in_([
                "active", "trialing", "grace", "past_due", "internal_test"
            ])
        ).order_by(OrgSubscription.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def get_entitlements(org_id, db: AsyncSession) -> dict:
    """Get frozen entitlements for an organization (from subscription snapshot)."""
    sub = await get_active_subscription(org_id, db)
    if not sub or not sub.entitlements_snapshot_json:
        return DEFAULT_FREE_ENTITLEMENTS
    return sub.entitlements_snapshot_json


async def resolve_effective_entitlements(org_id, db: AsyncSession,
                                          operation_type: str = "") -> dict:
    """Resolve effective entitlements with 7-level priority.

    Priority (high to low):
    1. EmergencyPause — highest, directly blocks
    2. Subscription.status (suspended/expired) — overrides plan
    3. System Owner org-level override
    4. FeatureFlag org-level override
    5. OrgSubscription entitlements_snapshot_json
    6. PlanDefinition defaults
    7. Platform default free entitlement
    """
    blocked_by = []
    source_trace = {}

    # 1. EmergencyPause check
    pauses = (await db.execute(
        select(EmergencyPause).where(
            EmergencyPause.status == "active",
            EmergencyPause.scope.in_(["global", "organization", "feature", "operation_type"]),
        )
    )).scalars().all()

    for pause in pauses:
        if pause.scope == "global":
            blocked_by.append(f"emergency_pause:global:{pause.reason}")
        elif pause.scope == "organization" and str(pause.organization_id) == str(org_id):
            blocked_by.append(f"emergency_pause:org:{pause.reason}")
        elif pause.scope == "operation_type" and pause.operation_type == operation_type:
            blocked_by.append(f"emergency_pause:op:{pause.reason}")

    # 2. Subscription status
    sub = await get_active_subscription(org_id, db)
    sub_status = sub.status if sub else "none"

    status_blocks = {
        "expired": "subscription_expired",
        "suspended": "subscription_suspended",
        "cancelled": "subscription_cancelled",
    }
    if sub_status in status_blocks:
        blocked_by.append(status_blocks[sub_status])

    # 5+6+7. Base entitlements
    if sub and sub.entitlements_snapshot_json:
        base = dict(sub.entitlements_snapshot_json)
        source_trace["base"] = f"subscription_snapshot:plan_version={sub.plan_version}"
    else:
        base = DEFAULT_FREE_ENTITLEMENTS
        source_trace["base"] = "default_free"

    # Apply subscription status overrides
    if sub_status == "grace":
        base["features"] = dict(base.get("features", {}))
    elif sub_status in ("expired", "past_due"):
        limited = dict(base.get("features", {}))
        for k in ("feature_benchmark", "feature_trends", "feature_cms_webhook",
                   "feature_cms_wordpress", "feature_api_access"):
            limited[k] = False
        base["features"] = limited
    elif sub_status == "suspended":
        base["features"] = {k: False for k in base.get("features", {})}
        base["limits"] = {k: 0 for k in base.get("limits", {})}

    # 4. FeatureFlag overrides
    flag_overrides = (await db.execute(
        select(FeatureFlagOverride).join(FeatureFlag).where(
            FeatureFlagOverride.organization_id == org_id,
            FeatureFlag.is_active == True,
        )
    )).scalars().all()

    for fo in flag_overrides:
        flag = (await db.execute(
            select(FeatureFlag).where(FeatureFlag.id == fo.feature_flag_id)
        )).scalar_one_or_none()
        if flag:
            flag_key = f"feature_{flag.key}"
            if flag.flag_type == "kill_switch":
                base["features"][flag_key] = False
                source_trace[flag_key] = f"feature_flag:kill_switch:{flag.key}"
            elif fo.enabled:
                base["features"][flag_key] = True
                source_trace[flag_key] = f"feature_flag:enabled:{flag.key}"
            else:
                base["features"][flag_key] = False
                source_trace[flag_key] = f"feature_flag:disabled:{flag.key}"

    # Apply override limits from subscription
    if sub:
        for limit_key in ("max_brands", "max_users", "max_api_keys", "max_cms_targets"):
            override_val = getattr(sub, f"override_{limit_key}", None)
            if override_val is not None and override_val >= 0:
                base["limits"][limit_key] = override_val

    # Build blocked_actions
    blocked_actions = {}
    limits = base.get("limits", {})
    features = base.get("features", {})

    if not features.get("feature_benchmark"):
        blocked_actions["view_benchmark"] = {
            "allowed": False, "reason_code": "ENTITLEMENT_DENIED",
            "message": "当前套餐不支持 Benchmark"
        }

    # Build response
    return {
        "plan": {"name": sub.plan_id if sub else "free", "tier": 0},
        "subscription_status": sub_status,
        "effective_features": features,
        "effective_limits": limits,
        "formats": base.get("formats", {}),
        "blocked_by": blocked_by,
        "blocked_actions": blocked_actions,
        "source_trace": source_trace,
    }


def check_feature(entitlements: dict, feature: str) -> bool:
    """Quick check if a feature is enabled."""
    return entitlements.get("effective_features", {}).get(feature, False)


def check_limit(entitlements: dict, limit_key: str) -> int:
    """Get a limit value (-1 = unlimited)."""
    return entitlements.get("effective_limits", {}).get(limit_key, 0)
