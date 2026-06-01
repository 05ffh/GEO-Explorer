"""Platform ViewModel — two-layer permission model (P0-3)."""
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.user import User


async def build_platform_vm(user: User, db: AsyncSession) -> dict:
    """Build platform console permissions ViewModel.

    Layer 1 — visible_pages: which pages the user can see (nav guard).
    Layer 2 — actions: which specific actions the user can perform (button guard).

    Backend API must also enforce these — frontend hiding is UX, not security.
    """
    is_owner = user.platform_role == "system_owner"
    is_admin = user.platform_role in ("system_owner", "system_admin")

    return {
        "user": {
            "name": user.name,
            "email": user.email,
            "platform_role": user.platform_role,
            "is_system_owner": is_owner,
            "is_system_admin": is_admin,
        },
        "visible_pages": {
            "platform_overview": is_admin,
            "organizations": is_admin,
            "plans": is_owner,
            "feature_flags": is_admin,
            "emergency_pause": is_admin,
            "audit_logs": is_admin,
            "data_deletion": is_owner,
        },
        "actions": {
            "organizations.view": is_admin,
            "organizations.suspend": is_owner,
            "organizations.resume": is_owner,
            "plans.create": is_owner,
            "plans.edit": is_owner,
            "plans.deprecate": is_owner,
            "feature_flags.create": is_owner,
            "feature_flags.edit": is_owner,
            "feature_flags.view": is_admin,
            "emergency_pause.global": is_owner,
            "emergency_pause.organization": is_admin,
            "emergency_pause.feature": is_owner,
            "emergency_pause.resolve": is_admin,
            "data_deletion.approve": is_owner,
            "data_deletion.reject": is_owner,
            "data_deletion.dry_run": is_owner,
            "audit_logs.view": is_admin,
            "internal_cost.view": is_owner,
        },
    }
