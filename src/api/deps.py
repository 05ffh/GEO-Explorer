from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from src.database import get_db
from src.config import settings
from src.models.user import User
import logging

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate from Authorization header or 'geo_token' cookie."""
    token = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("geo_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401)
    except JWTError:
        raise HTTPException(status_code=401)

    user = (await db.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401)
    return user


async def get_user_or_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via cookie/JWT or API Key header.

    Tries cookie/JWT first. Falls back to API Key (X-GEO-API-Key header).
    Returns a User in both cases.
    """
    # Try cookie/JWT auth first
    token = None
    if credentials:
        token_str = credentials.credentials
        if not token_str.startswith("geo_live_") and not token_str.startswith("geo_test_"):
            token = token_str
    else:
        cookie_token = request.cookies.get("geo_token")
        if cookie_token:
            token = cookie_token

    if token:
        try:
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[settings.jwt_algorithm],
            )
            user_id = payload.get("sub")
            if user_id:
                user = (await db.execute(
                    select(User).where(User.id == user_id)
                )).scalar_one_or_none()
                if user:
                    return user
        except JWTError:
            pass

    # Fall back to API Key auth
    from src.saas.api_key_auth import resolve_user_from_api_key
    result = await resolve_user_from_api_key(request, db)
    if result is None:
        raise HTTPException(status_code=401, detail="Not authenticated — provide a valid session cookie, JWT token, or API Key")

    user, api_key = result
    # Store API key on request state so routes can check auth method
    request.state.api_key = api_key
    return user


def require_api_scope(*required_scopes: str):
    """Authenticate via API Key only (no cookie fallback) with scope enforcement.

    Use for machine-to-machine endpoints where cookie auth is not appropriate.
    Returns (User, ApiKey).
    """
    async def verifier(request: Request, db: AsyncSession = Depends(get_db)):
        from src.saas.api_key_auth import require_api_key_scope as _require
        dep = _require(*required_scopes)
        return await dep(request, db)
    return verifier


def require_permission(permission: str):
    """FastAPI dependency: raise 403 with structured error if permission denied.

    Checks platform_role first (system_owner has all), then org role.
    """
    async def checker(user: User = Depends(get_current_user)):
        from src.auth.permissions import has_permission as _has_perm
        if not _has_perm(user.platform_role, user.role, permission):
            raise HTTPException(status_code=403, detail={
                "error": "permission_denied",
                "required": permission,
                "user_role": user.role,
                "platform_role": user.platform_role,
                "message": "你没有此操作的权限",
            })
        return user
    return checker


def require_platform_permission(permission: str):
    """FastAPI dependency: only platform roles can pass."""
    async def checker(user: User = Depends(get_current_user)):
        from src.auth.permissions import has_platform_permission
        if not has_platform_permission(user.platform_role, permission):
            raise HTTPException(status_code=403, detail={
                "error": "platform_permission_denied",
                "required": permission,
                "platform_role": user.platform_role,
                "message": "需要平台级权限",
            })
        return user
    return checker


async def get_org_brand_or_404(brand_id, user: User, db: AsyncSession):
    from src.models.brand import Brand
    brand = (await db.execute(
        select(Brand).where(
            Brand.id == brand_id,
            Brand.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand


async def get_org_gt_candidate_or_404(candidate_id, user: User, db: AsyncSession):
    """Fetch GT candidate, verify org ownership. Cross-org returns 404."""
    from src.models.gt_candidate import GroundTruthCandidate
    resource = (await db.execute(
        select(GroundTruthCandidate).where(GroundTruthCandidate.id == candidate_id)
    )).scalar_one_or_none()
    if not resource or resource.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Not found")
    return resource


async def get_org_action_theme_or_404(theme_id, user: User, db: AsyncSession):
    """Fetch ActionTheme, verify org ownership."""
    from src.models.action_theme import ActionTheme
    resource = (await db.execute(
        select(ActionTheme).where(ActionTheme.id == theme_id)
    )).scalar_one_or_none()
    if not resource or resource.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Not found")
    return resource


async def get_org_content_package_or_404(package_id, user: User, db: AsyncSession):
    """Fetch ContentPackage, verify org ownership."""
    from src.models.content_package import ContentPackage
    resource = (await db.execute(
        select(ContentPackage).where(ContentPackage.id == package_id)
    )).scalar_one_or_none()
    if not resource or resource.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Not found")
    return resource


async def get_org_hallucination_or_404(hallucination_id, user: User, db: AsyncSession):
    """Fetch HallucinationResult, verify org via brand."""
    from src.models.hallucination import HallucinationResult
    from src.models.brand import Brand
    h = (await db.execute(
        select(HallucinationResult).where(HallucinationResult.id == hallucination_id)
    )).scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Not found")
    brand = (await db.execute(select(Brand).where(Brand.id == h.brand_id))).scalar_one_or_none()
    if not brand or brand.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Not found")
    return h
