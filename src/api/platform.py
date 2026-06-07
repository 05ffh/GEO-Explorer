"""Platform admin API — system_owner/system_admin endpoints (P2-5)."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.organization import Organization
from src.models.saas import (PlanDefinition, OrgSubscription, FeatureFlag,
                               FeatureFlagOverride, EmergencyPause,
                               PlatformAdminProfile, PlatformAccessSession,
                               PlatformApprovalRequest, DataDeletionRequest)
from src.models.audit_log import AuditLog

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/platform", tags=["platform"])


def _check_system_admin(user: User):
    if user.platform_role not in ("system_owner", "system_admin"):
        raise HTTPException(403, "需要平台管理员权限")


def _check_system_owner(user: User):
    if user.platform_role != "system_owner":
        raise HTTPException(403, "需要 System Owner 权限")


# ── Organizations ─────────────────────────────────────────────────────────────

@router.get("/organizations")
async def list_organizations(user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db),
                              search: str = "", limit: int = 50, offset: int = 0):
    """List all organizations (system_admin+)."""
    _check_system_admin(user)
    q = select(Organization)
    if search:
        q = q.where(Organization.name.ilike(f"%{search}%"))
    q = q.order_by(desc(Organization.created_at)).offset(offset).limit(limit)
    result = await db.execute(q)
    orgs = result.scalars().all()

    return [{
        "id": str(o.id), "name": o.name, "slug": o.slug,
        "is_active": o.is_active, "plan": o.plan,
        "brand_count": o.brand_count, "user_count": o.user_count,
        "onboarding_step": o.onboarding_step,
        "created_at": o.created_at.isoformat() if o.created_at else "",
    } for o in orgs]


@router.get("/organizations/{org_id}")
async def get_organization(org_id: str, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Get organization details."""
    _check_system_admin(user)
    org = await db.get(Organization, uuid.UUID(org_id))
    if not org:
        raise HTTPException(404, "组织不存在")

    sub = (await db.execute(
        select(OrgSubscription).where(
            OrgSubscription.organization_id == org.id,
            OrgSubscription.status.in_(["active", "trialing", "grace", "past_due", "internal_test"])
        ).order_by(desc(OrgSubscription.created_at)).limit(1)
    )).scalar_one_or_none()

    return {
        "id": str(org.id), "name": org.name, "slug": org.slug,
        "is_active": org.is_active, "plan": org.plan,
        "brand_count": org.brand_count, "user_count": org.user_count,
        "onboarding_step": org.onboarding_step,
        "created_at": org.created_at.isoformat() if org.created_at else "",
        "subscription": {
            "status": sub.status, "plan_id": str(sub.plan_id),
            "plan_version": sub.plan_version,
            "current_cost_cny": float(sub.current_cost_cny) if sub.current_cost_cny else 0,
        } if sub else None,
    }


@router.patch("/organizations/{org_id}/suspend")
async def suspend_organization(org_id: str, request: Request,
                                user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    """Suspend an organization."""
    _check_system_admin(user)
    body = await request.json()
    reason = body.get("reason", "")

    org = await db.get(Organization, uuid.UUID(org_id))
    if not org:
        raise HTTPException(404, "组织不存在")

    org.is_active = False
    # Suspend subscription
    await db.execute(text(
        "UPDATE org_subscriptions SET status = 'suspended', suspension_reason = :r, "
        "suspended_at = :now, updated_at = :now "
        "WHERE organization_id = :oid AND status IN ('active','trialing','grace','past_due')"
    ), {"r": reason, "now": datetime.now(timezone.utc), "oid": org.id})
    await db.flush()
    return {"suspended": True, "organization_id": str(org.id)}


@router.patch("/organizations/{org_id}/resume")
async def resume_organization(org_id: str, request: Request,
                               user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """Resume a suspended organization."""
    _check_system_admin(user)
    org = await db.get(Organization, uuid.UUID(org_id))
    if not org:
        raise HTTPException(404, "组织不存在")

    org.is_active = True
    await db.execute(text(
        "UPDATE org_subscriptions SET status = 'active', suspension_reason = NULL, "
        "suspended_at = NULL, updated_at = :now "
        "WHERE organization_id = :oid AND status = 'suspended'"
    ), {"now": datetime.now(timezone.utc), "oid": org.id})
    await db.flush()
    return {"resumed": True, "organization_id": str(org.id)}


# ── Plans ─────────────────────────────────────────────────────────────────────

@router.get("/plans")
async def platform_list_plans(user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """List all plans including non-public (system_admin+)."""
    _check_system_admin(user)
    result = await db.execute(
        select(PlanDefinition).order_by(PlanDefinition.tier, PlanDefinition.version)
    )
    return [_plan_response(p) for p in result.scalars().all()]


@router.post("/plans")
async def create_plan(request: Request, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Create a new PlanDefinition (system_owner only)."""
    _check_system_owner(user)
    body = await request.json()
    plan = PlanDefinition(
        name=body["name"], display_name=body.get("display_name", body["name"]),
        tier=body.get("tier", 0), version=body.get("version", "1.0"),
        is_public=body.get("is_public", True), is_active=body.get("is_active", True),
        max_brands=body.get("max_brands", 1), max_users=body.get("max_users", 1),
        max_api_keys=body.get("max_api_keys", 0),
        features_json=body.get("features_json", {}),
        monthly_price_cny=body.get("monthly_price_cny"),
        yearly_price_cny=body.get("yearly_price_cny"),
    )
    db.add(plan)
    await db.flush()
    return _plan_response(plan)


@router.patch("/plans/{plan_id}")
async def update_plan(plan_id: str, request: Request,
                       user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Update a PlanDefinition (system_owner only)."""
    _check_system_owner(user)
    plan = await db.get(PlanDefinition, uuid.UUID(plan_id))
    if not plan:
        raise HTTPException(404, "套餐不存在")

    body = await request.json()
    for field in ("display_name", "is_public", "is_deprecated", "is_active",
                  "features_json", "monthly_price_cny", "yearly_price_cny"):
        if field in body:
            setattr(plan, field, body[field])
    # Update quotas
    for qfield in ("max_brands", "max_users", "max_api_keys", "max_competitors",
                   "max_cms_targets", "data_retention_days", "max_storage_mb"):
        if qfield in body:
            setattr(plan, qfield, body[qfield])

    plan.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return _plan_response(plan)


# ── Feature Flags ─────────────────────────────────────────────────────────────

@router.get("/feature-flags")
async def list_feature_flags(user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """List all feature flags."""
    _check_system_admin(user)
    result = await db.execute(select(FeatureFlag).order_by(FeatureFlag.key))
    return [{"id": str(f.id), "key": f.key, "flag_type": f.flag_type,
             "default_enabled": f.default_enabled, "description": f.description,
             "starts_at": f.starts_at.isoformat() if f.starts_at else None,
             "ends_at": f.ends_at.isoformat() if f.ends_at else None}
            for f in result.scalars().all()]


@router.post("/feature-flags")
async def create_feature_flag(request: Request, user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """Create a feature flag (system_owner only)."""
    _check_system_owner(user)
    body = await request.json()
    flag = FeatureFlag(
        key=body["key"], description=body.get("description", ""),
        flag_type=body.get("flag_type", "beta_feature"),
        default_enabled=body.get("default_enabled", False),
        starts_at=body.get("starts_at"), ends_at=body.get("ends_at"),
        created_by=user.id,
    )
    db.add(flag)
    await db.flush()
    return {"id": str(flag.id), "key": flag.key, "created": True}


@router.patch("/feature-flags/{flag_id}")
async def update_feature_flag(flag_id: str, request: Request,
                               user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """Update a feature flag."""
    _check_system_owner(user)
    flag = await db.get(FeatureFlag, uuid.UUID(flag_id))
    if not flag:
        raise HTTPException(404, "Feature Flag 不存在")
    body = await request.json()
    for field in ("description", "default_enabled", "flag_type", "starts_at", "ends_at"):
        if field in body:
            setattr(flag, field, body[field])
    await db.flush()
    return {"id": str(flag.id), "updated": True}


# ── Emergency Pause ───────────────────────────────────────────────────────────

@router.post("/emergency-pause")
async def create_emergency_pause(request: Request, user: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    """Trigger emergency pause (system_owner only)."""
    _check_system_owner(user)
    body = await request.json()
    if not body.get("reason"):
        raise HTTPException(400, "必须填写暂停原因")

    pause = EmergencyPause(
        scope=body.get("scope", "global"),
        organization_id=uuid.UUID(body["organization_id"]) if body.get("organization_id") else None,
        feature_key=body.get("feature_key"),
        operation_type=body.get("operation_type"),
        status="active", reason=body["reason"],
        risk_level=body.get("risk_level", "high"),
        created_by=user.id,
        starts_at=datetime.now(timezone.utc),
        expires_at=body.get("expires_at"),
    )
    db.add(pause)
    await db.flush()
    return {"id": str(pause.id), "scope": pause.scope, "status": "active",
            "message": "暂停已生效"}


@router.post("/emergency-resume")
async def resume_emergency(request: Request, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Resolve an emergency pause."""
    _check_system_owner(user)
    body = await request.json()
    pause_id = body.get("pause_id")
    reason = body.get("resume_reason", "")

    if pause_id:
        await db.execute(text(
            "UPDATE emergency_pauses SET status = 'resolved', resolved_by = :uid, "
            "resolved_at = :now WHERE id = :id"
        ), {"uid": user.id, "now": datetime.now(timezone.utc), "id": uuid.UUID(pause_id)})
    else:
        # Resolve all active
        await db.execute(text(
            "UPDATE emergency_pauses SET status = 'resolved', resolved_by = :uid, "
            "resolved_at = :now WHERE status = 'active'"
        ), {"uid": user.id, "now": datetime.now(timezone.utc)})
    await db.flush()
    return {"resumed": True, "message": "暂停已恢复"}


@router.get("/emergency-pauses")
async def list_emergency_pauses(user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """List active emergency pauses."""
    _check_system_admin(user)
    result = await db.execute(
        select(EmergencyPause).where(EmergencyPause.status == "active")
    )
    return [{"id": str(p.id), "scope": p.scope, "reason": p.reason,
             "risk_level": p.risk_level, "starts_at": p.starts_at.isoformat(),
             "expires_at": p.expires_at.isoformat() if p.expires_at else None}
            for p in result.scalars().all()]


# ── Audit Logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def list_audit_logs(user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db),
                           org_id: str = "", limit: int = 100, offset: int = 0):
    """List platform audit logs (system_admin+)."""
    _check_system_admin(user)
    q = "SELECT * FROM audit_logs WHERE 1=1"
    params = {}
    if org_id:
        q += " AND organization_id = :oid"
        params["oid"] = uuid.UUID(org_id)
    q += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset
    result = await db.execute(text(q), params)
    return [{"id": str(r.id), "action": r.action, "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
             "organization_id": str(r.organization_id) if r.organization_id else None,
             "resource_type": r.resource_type, "created_at": r.created_at.isoformat()}
            for r in result.fetchall()]


# ── Platform Usage ────────────────────────────────────────────────────────────

@router.get("/usage")
async def platform_usage(user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Get platform-wide usage stats (system_admin+)."""
    _check_system_admin(user)
    total_orgs = (await db.execute(text("SELECT COUNT(*) c FROM organizations WHERE is_active = true"))).scalar()
    total_brands = (await db.execute(text("SELECT COUNT(*) c FROM brands"))).scalar()
    total_users = (await db.execute(text("SELECT COUNT(*) c FROM users"))).scalar()
    total_keys = (await db.execute(text("SELECT COUNT(*) c FROM api_keys WHERE is_active = true AND revoked_at IS NULL"))).scalar()

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_tokens = (await db.execute(text(
        "SELECT COALESCE(SUM(total_tokens), 0) FROM api_usage_logs WHERE created_at >= :ms"
    ), {"ms": month_start})).scalar()

    return {
        "total_organizations": total_orgs,
        "total_brands": total_brands,
        "total_users": total_users,
        "total_active_api_keys": total_keys,
        "monthly_tokens": int(monthly_tokens or 0),
    }


# ── Platform Overview ──────────────────────────────────────────────────────────

@router.get("/overview")
async def platform_overview(user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """Platform overview dashboard (system_admin+)."""
    _check_system_admin(user)
    total_orgs = (await db.execute(text("SELECT COUNT(*) c FROM organizations"))).scalar()
    active_orgs = (await db.execute(text("SELECT COUNT(*) c FROM organizations WHERE is_active = true"))).scalar()
    total_brands = (await db.execute(text("SELECT COUNT(*) c FROM brands"))).scalar()
    total_users = (await db.execute(text("SELECT COUNT(*) c FROM users"))).scalar()
    active_keys = (await db.execute(text(
        "SELECT COUNT(*) c FROM api_keys WHERE is_active = true AND revoked_at IS NULL"
    ))).scalar()

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_tokens = (await db.execute(text(
        "SELECT COALESCE(SUM(total_tokens), 0) FROM api_usage_logs WHERE created_at >= :ms"
    ), {"ms": month_start})).scalar()

    active_pauses = (await db.execute(
        select(EmergencyPause).where(EmergencyPause.status == "active").limit(10)
    )).scalars().all()

    is_owner = user.platform_role == "system_owner"

    return {
        "org_count": total_orgs,
        "active_org_count": active_orgs,
        "brand_count": total_brands,
        "user_count": total_users,
        "active_api_key_count": active_keys,
        "monthly_tokens": int(monthly_tokens or 0),
        "active_emergency_pauses": [
            {"id": str(p.id), "scope": p.scope, "reason": p.reason,
             "risk_level": p.risk_level, "starts_at": p.starts_at.isoformat()}
            for p in active_pauses
        ],
        "can_view_internal_cost": is_owner,
    }


# ── Data Deletion Approval ────────────────────────────────────────────────────

@router.get("/data-deletion-requests")
async def list_deletion_requests(user: User = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    """List pending data deletion requests (system_owner)."""
    _check_system_owner(user)
    result = await db.execute(
        select(DataDeletionRequest).where(
            DataDeletionRequest.status.in_(["requested", "approved"])
        ).order_by(desc(DataDeletionRequest.created_at)).limit(50)
    )
    return [{"id": str(d.id), "organization_id": str(d.organization_id),
             "scope": d.scope, "status": d.status, "reason": d.reason,
             "requested_at": d.requested_at.isoformat() if d.requested_at else ""}
            for d in result.scalars().all()]


@router.post("/data-deletion-requests/{request_id}/approve")
async def approve_deletion(request_id: str, request: Request,
                            user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Approve a data deletion request (system_owner only, reason required)."""
    _check_system_owner(user)
    body = await request.json()
    reason = body.get("reason", "")
    if not reason:
        raise HTTPException(400, "审批删除请求必须填写原因")

    dr = await db.get(DataDeletionRequest, uuid.UUID(request_id))
    if not dr:
        raise HTTPException(404, "删除请求不存在")
    dr.status = "approved"
    dr.approved_by = user.id
    dr.scheduled_delete_at = datetime.now(timezone.utc) + datetime.timedelta(days=dr.retention_days)  # type: ignore[operator]
    await _write_audit(db, user, "approve_deletion", "data_deletion", str(dr.id),
                        dr.organization_id, {"reason": reason})
    await db.flush()
    return {"approved": True, "scheduled_delete_at": dr.scheduled_delete_at.isoformat()}


@router.post("/data-deletion-requests/{request_id}/reject")
async def reject_deletion(request_id: str, request: Request,
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """Reject a data deletion request (system_owner only, reason required)."""
    _check_system_owner(user)
    body = await request.json()
    reason = body.get("reason", "")
    if not reason:
        raise HTTPException(400, "拒绝删除请求必须填写原因")

    dr = await db.get(DataDeletionRequest, uuid.UUID(request_id))
    if not dr:
        raise HTTPException(404, "删除请求不存在")
    dr.status = "cancelled"
    dr.approved_by = user.id
    await _write_audit(db, user, "reject_deletion", "data_deletion", str(dr.id),
                        dr.organization_id, {"reason": reason})
    await db.flush()
    return {"rejected": True, "request_id": str(dr.id)}


@router.post("/data-deletion-requests/{request_id}/dry-run")
async def dry_run_deletion(request_id: str, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """Preview what would be deleted (system_owner only)."""
    _check_system_owner(user)
    dr = await db.get(DataDeletionRequest, uuid.UUID(request_id))
    if not dr:
        raise HTTPException(404, "删除请求不存在")

    # Count rows in affected tables (only existing tables with org_id column)
    from src.saas.deletion_task import DELETE_ORDER
    estimated = {}
    for table_name in DELETE_ORDER:
        has_col = (await db.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = 'organization_id')"
        ), {"t": table_name})).scalar()
        if not has_col:
            continue
        try:
            count = (await db.execute(text(
                f'SELECT COUNT(*) FROM "{table_name}" WHERE organization_id = :oid'
            ), {"oid": dr.organization_id})).scalar()
            if count:
                estimated[table_name] = count
        except Exception:
            pass  # table may not exist or have different schema

    result = {
        "request_id": str(dr.id), "organization_id": str(dr.organization_id),
        "scope": dr.scope, "brand_id": str(dr.brand_id) if dr.brand_id else None,
        "affected_tables": list(estimated.keys()),
        "estimated_delete_counts": estimated,
        "retained_items": [{"type": "security_audit", "reason": "保留 180 天"}],
        "backup_expiry_note": "备份将按备份保留策略自然过期",
        "risk_level": "high" if dr.scope == "organization" else "medium",
    }
    dr.dry_run_result_json = result
    await db.flush()
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _write_audit(db: AsyncSession, user: User, action: str, resource_type: str,
                       resource_id: str, org_id, metadata: dict = None):
    """Write an audit log entry for platform actions."""
    log = AuditLog(
        actor_user_id=user.id, organization_id=org_id,
        action=action, resource_type=resource_type, resource_id=resource_id,
        before_state=None, after_state=metadata, result="success",
    )
    db.add(log)


def _plan_response(p: PlanDefinition) -> dict:
    return {
        "id": str(p.id), "name": p.name, "display_name": p.display_name,
        "tier": p.tier, "version": p.version,
        "is_public": p.is_public, "is_deprecated": p.is_deprecated, "is_active": p.is_active,
        "max_brands": p.max_brands, "max_users": p.max_users,
        "max_api_keys": p.max_api_keys, "max_competitors": p.max_competitors,
        "data_retention_days": p.data_retention_days,
        "features": p.features_json,
        "monthly_price_cny": float(p.monthly_price_cny) if p.monthly_price_cny else None,
    }


# ── Platform Health ────────────────────────────────────────────────────────

@router.get("/health")
async def platform_health(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Platform health status — AI collector health for all platforms."""
    _check_system_admin(user)
    from src.view_models.platform_health import build_platform_health_vm
    return await build_platform_health_vm(db)
