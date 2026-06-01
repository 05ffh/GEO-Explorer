"""Quota checking with atomic FOR UPDATE + hard/soft limits (P2-5)."""
import logging
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.saas import OrgSubscription

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    def __init__(self, quota_type: str, limit: int, current: int,
                 upgrade_hint: str = ""):
        self.quota_type = quota_type
        self.limit = limit
        self.current = current
        self.upgrade_hint = upgrade_hint
        super().__init__(f"Quota {quota_type} exceeded: {current}/{limit}")


async def check_and_reserve_quota(db: AsyncSession, org_id, quota_type: str) -> bool:
    """Atomically check and reserve quota. Raises QuotaExceededError if over limit."""
    # Lock subscription row
    result = await db.execute(
        select(OrgSubscription).where(
            OrgSubscription.organization_id == org_id,
            OrgSubscription.status.in_([
                "active", "trialing", "grace", "past_due", "internal_test"
            ])
        ).order_by(OrgSubscription.created_at.desc()).limit(1).with_for_update()
    )
    sub = result.scalar_one_or_none()
    if not sub:
        return True  # No subscription = no quota, allow (free tier handled elsewhere)

    entitlements = sub.entitlements_snapshot_json or {}
    # Check overrides first
    override_map = {
        "brands": sub.override_max_brands,
        "users": sub.override_max_users,
        "api_keys": sub.override_max_api_keys,
        "cms_targets": sub.override_max_cms_targets,
    }
    limit = override_map.get(quota_type)
    if limit is None or limit < 0:
        limit = entitlements.get("limits", {}).get(f"max_{quota_type}", -1)

    if limit == -1:
        return True  # Unlimited

    current = await _count_active(db, org_id, quota_type)
    if current >= limit:
        hints = {
            "brands": "升级到 Pro 可创建最多 10 个品牌",
            "users": "升级到 Pro 可添加最多 5 位成员",
            "api_keys": "升级到 Enterprise 可使用 API Key",
            "cms_targets": "升级到 Enterprise 可添加更多发布目标",
        }
        raise QuotaExceededError(quota_type, limit, current, hints.get(quota_type, ""))

    return True


async def _count_active(db: AsyncSession, org_id, quota_type: str) -> int:
    """Count currently active resources for quota checking."""
    table_map = {
        "brands": ("brands", "organization_id", "TRUE"),
        "users": ("users", "organization_id", "TRUE"),
        "api_keys": ("api_keys", "organization_id", "is_active = true"),
        "cms_targets": ("publish_targets", "organization_id", "status = 'active'"),
        "competitors": ("competitor_sets", "organization_id", "TRUE"),
    }
    info = table_map.get(quota_type)
    if not info:
        return 0
    table, org_col, extra = info
    result = await db.execute(
        text(f"SELECT COUNT(*) c FROM {table} WHERE {org_col} = :oid AND {extra}"),
        {"oid": org_id}
    )
    row = result.fetchone()
    return row.c if row else 0


async def reconcole_org_usage_counts(db: AsyncSession, org_id) -> dict:
    """Reconcile cached usage counts with actual database counts."""
    counts = {}
    for qtype in ("brands", "users", "api_keys"):
        counts[qtype] = await _count_active(db, org_id, qtype)

    sub = (await db.execute(
        select(OrgSubscription).where(
            OrgSubscription.organization_id == org_id
        ).order_by(OrgSubscription.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    if sub:
        sub.current_brand_count = counts.get("brands", 0)
        sub.current_user_count = counts.get("users", 0)
        await db.flush()

    return counts
