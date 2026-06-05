from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from passlib.hash import bcrypt
from jose import jwt
from src.database import get_db
from src.config import settings
from src.models.user import User
from src.models.organization import Organization

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    org_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_name: str
    org_name: str


class SetupStatusResponse(BaseModel):
    needs_setup: bool


@router.get("/status", response_model=SetupStatusResponse)
async def auth_status(db: AsyncSession = Depends(get_db)):
    """Check if system needs first-time setup (no system_owner exists)."""
    existing = (await db.execute(
        select(User).where(User.platform_role == "system_owner")
    )).scalar_one_or_none()
    return SetupStatusResponse(needs_setup=existing is None)


@router.post("/setup", response_model=TokenResponse)
async def setup(body: SetupRequest, db: AsyncSession = Depends(get_db)):
    """First-time setup: create system_owner. Only works when no system_owner exists."""
    existing_owner = (await db.execute(
        select(User).where(User.platform_role == "system_owner")
    )).scalar_one_or_none()
    if existing_owner:
        raise HTTPException(status_code=403, detail="System already set up")

    existing_email = (await db.execute(
        select(User).where(User.email == body.email)
    )).scalar_one_or_none()
    if existing_email:
        raise HTTPException(status_code=409, detail="Email already registered")

    org = Organization(name=body.org_name)
    db.add(org)
    await db.flush()

    user = User(
        organization_id=org.id,
        email=body.email,
        name=body.name,
        role="admin",
        platform_role="system_owner",
        password_hash=bcrypt.hash(body.password),
    )
    db.add(user)
    await db.commit()

    token = _create_token(str(user.id))
    return TokenResponse(
        access_token=token, user_name=user.name, org_name=org.name,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(
        select(User).where(User.email == body.email)
    )).scalar_one_or_none()
    if not user or not bcrypt.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    org = (await db.execute(
        select(Organization).where(Organization.id == user.organization_id)
    )).scalar_one()

    token = _create_token(str(user.id))
    return TokenResponse(
        access_token=token, user_name=user.name, org_name=org.name,
    )


def _create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
