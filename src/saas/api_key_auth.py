"""API Key authentication — FastAPI dependency injection (P2-5)."""
import hashlib
import logging
from datetime import datetime, timezone
from fastapi import Request, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.saas import ApiKey, ApiKeyUsageLog
from src.models.user import User
from src.database import get_db

logger = logging.getLogger(__name__)

API_KEY_HEADER = "X-GEO-API-Key"
API_KEY_PREFIX = "geo_live_"
TEST_KEY_PREFIX = "geo_test_"

# Scope → endpoint mapping
SCOPE_ENDPOINT_MAP = {
    "brands:read":    [("GET", "/api/brands")],
    "brands:write":   [("POST", "/api/brands"), ("PATCH", "/api/brands"), ("DELETE", "/api/brands")],
    "collections:read": [("GET", "/api/collection-runs")],
    "collections:run":  [("POST", "/api/collection-runs")],
    "reports:read":     [("GET", "/api/reports"), ("GET", "/api/brands/")],
    "reports:generate": [("POST", "/api/reports/generate"), ("POST", "/api/brands/")],
    "exports:create":   [("POST", "/api/saas/data-exports"), ("POST", "/api/data-exports")],
    "cms:publish":      [("POST", "/api/publishing"), ("POST", "/api/content-packages/")],
    "usage:read":       [("GET", "/api/usage"), ("GET", "/api/saas/entitlements")],
    "admin:manage":     [],  # Full access, checked separately
}


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(f"geo_explorer_salt_{raw_key}".encode()).hexdigest()


def generate_api_key(key_type: str = "live") -> tuple[str, str, str]:
    import secrets
    raw = secrets.token_hex(32)
    prefix = API_KEY_PREFIX if key_type == "live" else TEST_KEY_PREFIX
    return raw, prefix, hash_api_key(raw)


def require_api_key_scope(*required_scopes: str):
    """FastAPI dependency: require API Key with scopes. Returns (User, ApiKey).

    Raises 401 for missing/invalid/expired/revoked keys.
    Raises 403 for IP mismatch or insufficient scopes.
    """
    async def verifier(request: Request, db: AsyncSession = Depends(get_db)):
        result = await resolve_user_from_api_key(request, db)
        if result is None:
            raise HTTPException(401, {"error_code": "API_KEY_REQUIRED", "message": "此接口需要 API Key 认证"})

        user, api_key = result

        if "admin:manage" not in (api_key.scopes_json or []):
            for scope in required_scopes:
                if scope not in (api_key.scopes_json or []):
                    raise HTTPException(403, {
                        "error_code": "API_KEY_SCOPE_DENIED",
                        "message": f"缺少 scope: {scope}",
                        "required": scope,
                    })

        return user, api_key

    return verifier


# Simple check without scope (for backward compat)
async def authenticate_api_key(request: Request, db: AsyncSession = Depends(get_db)):
    """Legacy: authenticate API Key without scope check. Returns (User, ApiKey)."""
    verifier = require_api_key_scope()
    return await verifier(request, db)


async def resolve_user_from_api_key(request: Request, db: AsyncSession) -> tuple[User, ApiKey] | None:
    """Validate API Key header and return (User, ApiKey) if present and valid.

    Returns None if no API Key header is present (caller should fall back to cookie auth).
    Raises HTTPException for invalid/expired/revoked keys.
    """
    raw_key = request.headers.get(API_KEY_HEADER, "")
    if not raw_key:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and not auth.startswith("Bearer eyJ"):
            raw_key = auth[7:]

    if not raw_key:
        return None

    if not (raw_key.startswith(API_KEY_PREFIX) or raw_key.startswith(TEST_KEY_PREFIX)):
        return None

    # Strip prefix before hashing — stored hash is for raw hex only
    if raw_key.startswith(API_KEY_PREFIX):
        raw_key = raw_key[len(API_KEY_PREFIX):]
    elif raw_key.startswith(TEST_KEY_PREFIX):
        raw_key = raw_key[len(TEST_KEY_PREFIX):]

    key_hash = hash_api_key(raw_key)
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(401, {"error_code": "API_KEY_INVALID", "message": "API Key 无效"})
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise HTTPException(401, {"error_code": "API_KEY_EXPIRED", "message": "API Key 已过期"})
    if api_key.revoked_at:
        raise HTTPException(401, {"error_code": "API_KEY_REVOKED", "message": "API Key 已被撤销"})

    if api_key.allowed_ips:
        client_ip = request.client.host if request.client else ""
        if client_ip not in api_key.allowed_ips:
            raise HTTPException(403, {"error_code": "IP_NOT_ALLOWED", "message": "IP 不在白名单内"})

    user = await db.get(User, api_key.user_id)
    if not user:
        raise HTTPException(401, {"error_code": "API_KEY_ORPHANED", "message": "API Key 关联用户不存在"})

    api_key.last_used_at = datetime.now(timezone.utc)
    api_key.usage_count = (api_key.usage_count or 0) + 1
    api_key.last_used_ip_hash = hashlib.sha256(
        (request.client.host if request.client else "").encode()
    ).hexdigest()

    log_entry = ApiKeyUsageLog(
        organization_id=api_key.organization_id, api_key_id=api_key.id,
        endpoint=request.url.path, method=request.method,
        status_code=0, ip_hash=api_key.last_used_ip_hash,
        user_agent=request.headers.get("User-Agent", ""),
        request_id=request.headers.get("X-Request-ID", ""),
    )
    db.add(log_entry)

    return user, api_key
