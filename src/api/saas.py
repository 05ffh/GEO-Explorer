"""SaaS API endpoints — entitlements, plans, subscriptions, api-keys, invites (P2-5)."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, get_current_user
from src.models.user import User
from src.models.saas import (PlanDefinition, OrgSubscription, ApiKey, OrgInvite,
                               DataExport, DataDeletionRequest, DeletionReceipt)
from src.saas.entitlement import (resolve_effective_entitlements, get_active_subscription,
                                    DEFAULT_FREE_ENTITLEMENTS)
from src.saas.api_key_auth import generate_api_key as _gen_key, hash_api_key
from src.saas.quota import check_and_reserve_quota, QuotaExceededError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/saas", tags=["saas"])


def _is_admin(user: User) -> bool:
    return user.has_permission("org:admin") if hasattr(user, "has_permission") else (user.role in ("owner", "admin"))


def _is_owner(user: User) -> bool:
    return user.role == "owner"


def _check_admin(user: User):
    if not _is_admin(user):
        raise HTTPException(403, "需要管理员权限")


def _check_owner(user: User):
    if not _is_owner(user):
        raise HTTPException(403, "需要组织 Owner 权限")


# ── Entitlements ──────────────────────────────────────────────────────────────

@router.get("/entitlements")
async def get_entitlements(user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Get effective entitlements for the current organization."""
    result = await resolve_effective_entitlements(user.organization_id, db)

    # Add usage counts
    sub = await get_active_subscription(user.organization_id, db)
    usage = {}
    if sub:
        usage = {
            "brands": sub.current_brand_count or 0,
            "users": sub.current_user_count or 0,
            "api_keys": (await db.execute(text(
                "SELECT COUNT(*) c FROM api_keys WHERE organization_id = :oid AND is_active = true"
            ), {"oid": user.organization_id})).scalar() or 0,
        }

    limits = result.get("effective_limits", {})
    warnings = []
    for key, label in [("max_brands", "品牌"), ("max_users", "成员"), ("max_api_keys", "API Key")]:
        limit = limits.get(key, -1)
        current = usage.get(key.replace("max_", ""), 0)
        if limit > 0:
            pct = current / limit
            if pct >= 1.0:
                warnings.append(f"{label}数已达上限 ({current}/{limit})")
            elif pct >= 0.8:
                warnings.append(f"{label}数接近上限 ({current}/{limit})")

    return {
        "plan": result.get("plan", {}),
        "subscription_status": result.get("subscription_status"),
        "effective_features": result.get("effective_features", {}),
        "effective_limits": limits,
        "formats": result.get("formats", {}),
        "usage": usage,
        "warnings": warnings,
        "blocked_by": result.get("blocked_by", []),
        "blocked_actions": result.get("blocked_actions", {}),
        "source_trace": result.get("source_trace", {}),
    }


# ── Plans ─────────────────────────────────────────────────────────────────────

@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db)):
    """List public plans for the pricing page."""
    result = await db.execute(
        select(PlanDefinition).where(
            PlanDefinition.is_public == True,
            PlanDefinition.is_deprecated == False,
            PlanDefinition.is_active == True,
        ).order_by(PlanDefinition.tier)
    )
    plans = result.scalars().all()
    return [{
        "name": p.name, "display_name": p.display_name, "tier": p.tier,
        "version": p.version,
        "max_brands": p.max_brands, "max_users": p.max_users,
        "max_competitors": p.max_competitors, "max_api_keys": p.max_api_keys,
        "data_retention_days": p.data_retention_days,
        "features": p.features_json,
        "monthly_price_cny": float(p.monthly_price_cny) if p.monthly_price_cny else None,
        "yearly_price_cny": float(p.yearly_price_cny) if p.yearly_price_cny else None,
    } for p in plans]


# ── Subscription ──────────────────────────────────────────────────────────────

@router.get("/subscription")
async def get_subscription(user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Get current organization subscription status."""
    sub = await get_active_subscription(user.organization_id, db)
    if not sub:
        return {"plan": "free", "status": "active"}
    plan = (await db.execute(
        select(PlanDefinition).where(PlanDefinition.id == sub.plan_id)
    )).scalar_one_or_none()
    return {
        "plan_name": plan.name if plan else "unknown",
        "plan_version": sub.plan_version,
        "status": sub.status,
        "started_at": sub.started_at.isoformat() if sub.started_at else None,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "current_brand_count": sub.current_brand_count,
        "current_user_count": sub.current_user_count,
        "pending_change": {
            "change_type": sub.pending_change_type,
            "effective_at": sub.pending_change_effective_at.isoformat() if sub.pending_change_effective_at else None,
        } if sub.pending_change_type else None,
    }


@router.post("/plan-change-preview")
async def preview_plan_change(request: Request, user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    """Preview the impact of a plan change."""
    _check_owner(user)
    body = await request.json()
    target_name = body.get("target_plan", "pro")

    target = (await db.execute(
        select(PlanDefinition).where(PlanDefinition.name == target_name, PlanDefinition.is_active == True)
    )).scalar_one_or_none()
    if not target:
        raise HTTPException(404, "套餐不存在")

    current = await resolve_effective_entitlements(user.organization_id, db)
    current_limits = current.get("effective_limits", {})

    target_features = target.features_json or {}
    impacts = {
        "brands_over_limit": [],
        "users_over_limit": [],
        "features_lost": [],
        "features_gained": [],
        "data_retention_change": f"{current_limits.get('data_retention_days', 90)} → {target.data_retention_days} 天",
    }

    sub = await get_active_subscription(user.organization_id, db)
    if target.max_brands >= 0 and sub and sub.current_brand_count > target.max_brands:
        impacts["brands_over_limit"].append(f"{sub.current_brand_count} → 限制 {target.max_brands}")

    for feat in current.get("effective_features", {}):
        if current["effective_features"][feat] and not target_features.get(feat):
            impacts["features_lost"].append(feat)
    for feat in target_features:
        if target_features[feat] and not current.get("effective_features", {}).get(feat):
            impacts["features_gained"].append(feat)

    return {"target_plan": target_name, "target_version": target.version, "impacts": impacts}


# ── API Keys ──────────────────────────────────────────────────────────────────

@router.get("/api-keys")
async def list_api_keys(user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """List API keys for the current organization."""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.organization_id == user.organization_id,
            ApiKey.revoked_at.is_(None),
        ).order_by(desc(ApiKey.created_at))
    )
    keys = result.scalars().all()
    return [{
        "id": str(k.id), "name": k.name, "key_prefix": k.key_prefix,
        "key_type": k.key_type, "scopes": k.scopes_json,
        "is_active": k.is_active, "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
        "expires_at": k.expires_at.isoformat() if k.expires_at else None,
        "usage_count": k.usage_count,
    } for k in keys]


@router.post("/api-keys")
async def create_api_key(request: Request, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Create a new API key. Full key shown only once."""
    _check_admin(user)

    # Quota check
    try:
        await check_and_reserve_quota(db, user.organization_id, "api_keys")
    except QuotaExceededError as e:
        raise HTTPException(403, {"error_code": "QUOTA_EXCEEDED", "message": str(e),
                                   "upgrade_hint": e.upgrade_hint})

    body = await request.json()
    name = body.get("name", "").strip()
    key_type = body.get("key_type", "live")
    scopes = body.get("scopes", ["brands:read"])

    if not name:
        raise HTTPException(400, "name 不能为空")
    if key_type not in ("live", "test", "service"):
        raise HTTPException(400, "无效的 key_type")

    raw_key, prefix, key_hash = _gen_key(key_type)

    api_key = ApiKey(
        organization_id=user.organization_id, user_id=user.id,
        name=name, key_type=key_type, key_prefix=prefix, key_hash=key_hash,
        scopes_json=scopes,
        expires_at=body.get("expires_at"),
        allowed_ips=body.get("allowed_ips"),
        rate_limit_per_minute=body.get("rate_limit_per_minute"),
    )
    db.add(api_key)
    await db.flush()

    return {
        "id": str(api_key.id), "name": name, "key_prefix": prefix,
        "api_key": raw_key,  # Only shown once
        "scopes": scopes, "key_type": key_type,
        "message": "请立即保存此密钥，关闭后将无法再次查看",
    }


@router.post("/api-keys/{key_id}/rotate")
async def rotate_api_key(key_id: str, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Rotate an API key — revoke old, create new."""
    _check_admin(user)
    old_key = await db.get(ApiKey, uuid.UUID(key_id))
    if not old_key or str(old_key.organization_id) != str(user.organization_id):
        raise HTTPException(404, "API Key 不存在")

    raw_key, prefix, key_hash = _gen_key(old_key.key_type)
    new_key = ApiKey(
        organization_id=user.organization_id, user_id=user.id,
        name=f"{old_key.name} (rotated)", key_type=old_key.key_type,
        key_prefix=prefix, key_hash=key_hash,
        scopes_json=old_key.scopes_json,
        rotated_from_key_id=old_key.id,
        expires_at=old_key.expires_at,
    )
    db.add(new_key)
    old_key.revoked_at = datetime.now(timezone.utc)
    old_key.revoked_by = user.id
    old_key.revocation_reason = "rotated"
    old_key.is_active = False
    await db.flush()

    return {"id": str(new_key.id), "api_key": raw_key, "key_prefix": prefix,
            "message": "密钥已轮换，请保存新密钥"}


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Revoke an API key."""
    _check_admin(user)
    key = await db.get(ApiKey, uuid.UUID(key_id))
    if not key or str(key.organization_id) != str(user.organization_id):
        raise HTTPException(404, "API Key 不存在")
    key.revoked_at = datetime.now(timezone.utc)
    key.revoked_by = user.id
    key.revocation_reason = "manual_revoke"
    key.is_active = False
    await db.flush()
    return {"revoked": True}


# ── Invites ───────────────────────────────────────────────────────────────────

@router.get("/invites")
async def list_invites(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """List pending invites for the organization."""
    _check_admin(user)
    result = await db.execute(
        select(OrgInvite).where(
            OrgInvite.organization_id == user.organization_id,
            OrgInvite.status == "pending",
        ).order_by(desc(OrgInvite.created_at))
    )
    return [{"id": str(i.id), "email": i.email, "role": i.role,
             "status": i.status, "expires_at": i.expires_at.isoformat(),
             "created_at": i.created_at.isoformat()}
            for i in result.scalars().all()]


@router.post("/invites")
async def create_invite(request: Request, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Create a member invite."""
    _check_admin(user)
    body = await request.json()
    email = body.get("email", "").strip().lower()
    role = body.get("role", "viewer")

    if not email:
        raise HTTPException(400, "email 不能为空")

    # Check seat quota
    try:
        await check_and_reserve_quota(db, user.organization_id, "users")
    except QuotaExceededError as e:
        raise HTTPException(403, {"error_code": "INVITE_SEAT_QUOTA_EXCEEDED",
                                   "message": str(e)})

    # Check duplicate pending
    dup = (await db.execute(
        select(OrgInvite).where(
            OrgInvite.organization_id == user.organization_id,
            OrgInvite.email == email, OrgInvite.status == "pending",
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(409, "该邮箱已有待接受的邀请")

    import secrets
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    invite = OrgInvite(
        organization_id=user.organization_id, invited_by=user.id,
        email=email, role=role, token_hash=token_hash,
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    await db.flush()

    return {"id": str(invite.id), "email": email, "role": role,
            "invite_token": raw_token,  # For MVP: return token directly
            "expires_at": invite.expires_at.isoformat()}


@router.post("/invites/{token}/accept")
async def accept_invite(token: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Accept a member invite."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    invite = (await db.execute(
        select(OrgInvite).where(OrgInvite.token_hash == token_hash)
    )).scalar_one_or_none()

    if not invite:
        raise HTTPException(404, "邀请不存在")
    if invite.status != "pending":
        raise HTTPException(400, "邀请已失效")
    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = "expired"
        await db.flush()
        raise HTTPException(400, "邀请已过期")

    # Update user's org and role
    user.organization_id = invite.organization_id
    user.role = invite.role
    invite.status = "accepted"
    invite.accepted_by = user.id
    await db.flush()
    return {"accepted": True, "organization_id": str(invite.organization_id)}


@router.post("/invites/{invite_id}/revoke")
async def revoke_invite(invite_id: str, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Revoke a pending invite."""
    _check_admin(user)
    invite = await db.get(OrgInvite, uuid.UUID(invite_id))
    if not invite or str(invite.organization_id) != str(user.organization_id):
        raise HTTPException(404, "邀请不存在")
    invite.status = "revoked"
    await db.flush()
    return {"revoked": True}


# ── Data Exports ──────────────────────────────────────────────────────────────

@router.get("/data-exports")
async def list_exports(user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """List data exports for the organization."""
    result = await db.execute(
        select(DataExport).where(
            DataExport.organization_id == user.organization_id,
        ).order_by(desc(DataExport.created_at)).limit(50)
    )
    return [{"id": str(e.id), "scope": e.scope, "format": e.format,
             "status": e.status, "redaction_level": e.redaction_level,
             "file_size_bytes": e.file_size_bytes,
             "download_count": e.download_count,
             "expires_at": e.expires_at.isoformat() if e.expires_at else None,
             "created_at": e.created_at.isoformat()}
            for e in result.scalars().all()]


@router.post("/data-exports")
async def create_export(request: Request, user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """Request a data export."""
    _check_owner(user)
    body = await request.json()
    scope = body.get("scope", "brand")
    brand_id = body.get("brand_id")
    fmt = body.get("format", "json")
    redaction = body.get("redaction_level", "full")

    exp = DataExport(
        organization_id=user.organization_id, user_id=user.id,
        scope=scope, brand_id=uuid.UUID(brand_id) if brand_id else None,
        format=fmt, redaction_level=redaction,
        status="queued", requested_by_role=user.role,
        export_reason=body.get("reason", ""),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=72),
    )
    db.add(exp)
    await db.flush()

    return {"id": str(exp.id), "status": "queued",
            "expires_at": exp.expires_at.isoformat()}


@router.get("/data-exports/{export_id}")
async def get_export(export_id: str, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """Get a single export's details."""
    exp = await db.get(DataExport, uuid.UUID(export_id))
    if not exp or exp.organization_id != user.organization_id:
        raise HTTPException(404, "导出不存在")
    return {"id": str(exp.id), "scope": exp.scope, "format": exp.format,
            "status": exp.status, "redaction_level": exp.redaction_level,
            "file_size_bytes": exp.file_size_bytes, "file_hash": exp.file_hash,
            "download_count": exp.download_count, "max_downloads": exp.max_downloads,
            "last_downloaded_at": exp.last_downloaded_at.isoformat() if exp.last_downloaded_at else None,
            "expires_at": exp.expires_at.isoformat() if exp.expires_at else None,
            "revoked_at": exp.revoked_at.isoformat() if exp.revoked_at else None,
            "created_at": exp.created_at.isoformat()}


@router.post("/data-exports/{export_id}/revoke")
async def revoke_export(export_id: str, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Revoke an export's download token."""
    exp = await db.get(DataExport, uuid.UUID(export_id))
    if not exp or exp.organization_id != user.organization_id:
        raise HTTPException(404, "导出不存在")
    exp.revoked_at = datetime.now(timezone.utc)
    exp.download_token_hash = None
    await db.flush()
    return {"revoked": True, "export_id": str(exp.id)}


@router.post("/data-exports/{export_id}/retry")
async def retry_export(export_id: str, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Retry a failed export."""
    exp = await db.get(DataExport, uuid.UUID(export_id))
    if not exp or exp.organization_id != user.organization_id:
        raise HTTPException(404, "导出不存在")
    if exp.status != "failed":
        raise HTTPException(400, "只有失败的导出可以重试")
    exp.status = "queued"
    await db.flush()
    return {"retried": True, "export_id": str(exp.id)}


# ── Data Deletion ─────────────────────────────────────────────────────────────

@router.get("/data-deletion-requests")
async def list_deletion_requests(user: User = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    """List data deletion requests for the organization."""
    _check_owner(user)
    result = await db.execute(
        select(DataDeletionRequest).where(
            DataDeletionRequest.organization_id == user.organization_id,
        ).order_by(desc(DataDeletionRequest.created_at)).limit(50)
    )
    return [{"id": str(d.id), "scope": d.scope, "status": d.status,
             "reason": d.reason, "requested_at": d.requested_at.isoformat() if d.requested_at else "",
             "scheduled_delete_at": d.scheduled_delete_at.isoformat() if d.scheduled_delete_at else None}
            for d in result.scalars().all()]


@router.get("/data-deletion-requests/{request_id}")
async def get_deletion_request(request_id: str, user: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    """Get a single deletion request's details."""
    dr = await db.get(DataDeletionRequest, uuid.UUID(request_id))
    if not dr or dr.organization_id != user.organization_id:
        raise HTTPException(404, "删除请求不存在")
    return {"id": str(dr.id), "scope": dr.scope, "status": dr.status,
            "reason": dr.reason, "requested_at": dr.requested_at.isoformat() if dr.requested_at else "",
            "scheduled_delete_at": dr.scheduled_delete_at.isoformat() if dr.scheduled_delete_at else None,
            "completed_at": dr.completed_at.isoformat() if dr.completed_at else None,
            "failed_table": dr.failed_table, "failed_reason": dr.failed_reason,
            "retry_count": dr.retry_count, "retention_days": dr.retention_days}


@router.post("/data-deletion-requests")
async def create_deletion_request(request: Request, user: User = Depends(get_current_user),
                                    db: AsyncSession = Depends(get_db)):
    """Request data deletion."""
    _check_owner(user)
    body = await request.json()
    scope = body.get("scope", "brand")
    brand_id = body.get("brand_id")
    reason = body.get("reason", "")

    if not reason:
        raise HTTPException(400, "必须填写删除原因")

    dr = DataDeletionRequest(
        organization_id=user.organization_id, requested_by=user.id,
        scope=scope, brand_id=uuid.UUID(brand_id) if brand_id else None,
        status="requested", reason=reason,
        retention_days=90,
        scheduled_delete_at=datetime.now(timezone.utc) + timedelta(days=90),
    )
    db.add(dr)
    await db.flush()

    return {"id": str(dr.id), "status": "requested",
            "scheduled_delete_at": dr.scheduled_delete_at.isoformat()}


@router.post("/data-deletion-requests/dry-run")
async def dry_run_org_deletion(request: Request, user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    """Preview what would be deleted for a scoped deletion."""
    _check_owner(user)
    body = await request.json()
    scope = body.get("scope", "brand")
    brand_id = body.get("brand_id")
    oid = user.organization_id

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
            if scope == "brand" and brand_id:
                has_brand = (await db.execute(text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = 'brand_id')"
                ), {"t": table_name})).scalar()
                if has_brand:
                    count = (await db.execute(text(
                        f'SELECT COUNT(*) FROM "{table_name}" WHERE brand_id = :bid'
                    ), {"bid": uuid.UUID(brand_id)})).scalar()
                else:
                    count = (await db.execute(text(
                        f'SELECT COUNT(*) FROM "{table_name}" WHERE organization_id = :oid'
                    ), {"oid": oid})).scalar()
            else:
                count = (await db.execute(text(
                    f'SELECT COUNT(*) FROM "{table_name}" WHERE organization_id = :oid'
                ), {"oid": oid})).scalar()
            if count:
                estimated[table_name] = count
        except Exception:
            pass

    return {"scope": scope, "brand_id": brand_id,
            "affected_tables": list(estimated.keys()),
            "estimated_delete_counts": estimated,
            "retained_items": [{"type": "security_audit", "reason": "保留 180 天"}],
            "risk_level": "high" if scope == "organization" else "medium"}


@router.post("/data-deletion-requests/{request_id}/cancel")
async def cancel_deletion_request(request_id: str, user: User = Depends(get_current_user),
                                    db: AsyncSession = Depends(get_db)):
    """Cancel a pending deletion request."""
    dr = await db.get(DataDeletionRequest, uuid.UUID(request_id))
    if not dr or dr.organization_id != user.organization_id:
        raise HTTPException(404, "删除请求不存在")
    if dr.status not in ("requested", "approved"):
        raise HTTPException(400, f"状态 {dr.status} 不可取消")
    dr.status = "cancelled"
    await db.flush()
    return {"cancelled": True, "request_id": str(dr.id)}


@router.get("/data-deletion-requests/{request_id}/receipt")
async def get_deletion_receipt(request_id: str, user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """Get the DeletionReceipt for a completed deletion request."""
    from src.models.saas import DeletionReceipt
    dr = await db.get(DataDeletionRequest, uuid.UUID(request_id))
    if not dr or dr.organization_id != user.organization_id:
        raise HTTPException(404, "删除请求不存在")
    if dr.status not in ("completed", "completed_with_warnings"):
        raise HTTPException(404, "收据仅在删除完成后可查看")

    result = await db.execute(
        select(DeletionReceipt).where(DeletionReceipt.deletion_request_id == dr.id)
    )
    receipt = result.scalar_one_or_none()
    if not receipt:
        return {"message": "收据尚未生成"}
    return {
        "request_id": str(receipt.deletion_request_id),
        "scope": receipt.scope, "brand_id": str(receipt.brand_id) if receipt.brand_id else None,
        "affected_tables": receipt.affected_tables_json,
        "deleted_counts": receipt.deleted_counts_json,
        "retained_items": receipt.retained_items_json,
        "file_deleted_count": receipt.file_deleted_count,
        "file_failed_count": receipt.file_failed_count,
        "failed_assets": receipt.failed_assets_json,
        "backup_expiry_note": receipt.backup_expiry_note,
        "receipt_hash": receipt.receipt_hash,
        "started_at": receipt.started_at.isoformat(),
        "completed_at": receipt.completed_at.isoformat(),
    }


# ── Registration ──────────────────────────────────────────────────────────────

@router.post("/register")
async def register(request: Request, db: AsyncSession = Depends(get_db)):
    """Self-service registration: creates Organization + User + Subscription."""
    body = await request.json()
    email = body.get("email", "").strip().lower()
    password = body.get("password", "").strip()
    org_name = body.get("organization_name", "").strip()
    org_slug = body.get("slug", "").strip() or org_name.lower().replace(" ", "-")
    accepted_terms = body.get("accepted_terms", False)

    if not all([email, password, org_name]):
        raise HTTPException(400, "email/password/organization_name 不能为空")
    if not accepted_terms:
        raise HTTPException(400, "必须同意服务条款")
    if len(password) < 8:
        raise HTTPException(400, "密码长度至少 8 位")

    # Disposable email check
    disposable_domains = {"mailinator.com", "tempmail.com", "10minutemail.com", "guerrillamail.com",
                          "sharklasers.com", "yopmail.com", "throwaway.email", "trashmail.com"}
    domain = email.split("@")[-1] if "@" in email else ""
    if domain in disposable_domains:
        raise HTTPException(400, "不支持一次性邮箱注册")

    # Check email uniqueness
    existing_user = (await db.execute(
        text("SELECT id FROM users WHERE email = :email"), {"email": email}
    )).fetchone()
    if existing_user:
        raise HTTPException(409, "该邮箱已注册")

    # Check slug uniqueness
    existing_slug = (await db.execute(
        text("SELECT id FROM organizations WHERE slug = :slug"), {"slug": org_slug}
    )).fetchone()
    if existing_slug:
        raise HTTPException(409, "该组织标识已被使用")

    # Get Free plan
    free_plan = (await db.execute(
        select(PlanDefinition).where(
            PlanDefinition.name == "free", PlanDefinition.is_active == True
        ).limit(1)
    )).scalar_one_or_none()

    try:
        import hashlib
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        from src.models.organization import Organization as OrgModel

        org = OrgModel(name=org_name, plan="free", slug=org_slug, is_active=True, onboarding_step=0)
        db.add(org)
        await db.flush()

        user_obj = User(organization_id=org.id, email=email, name=email.split("@")[0],
                        role="owner", password_hash=pwd_hash, email_verified=False)
        db.add(user_obj)
        await db.flush()

        if free_plan:
            db.add(OrgSubscription(
                organization_id=org.id, plan_id=free_plan.id,
                plan_version=free_plan.version, status="active",
            ))
            await db.flush()

        await db.commit()
        return {"organization_id": str(org.id), "user_id": str(user_obj.id),
                "plan": "free", "email_verified": False, "message": "注册成功"}
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error(f"Registration failed: {exc}")
        raise HTTPException(500, "注册失败，请重试")
