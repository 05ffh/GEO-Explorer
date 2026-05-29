# GEO Explorer — Action Workbench ViewModel
from sqlalchemy import select, desc
from src.models.action_theme import ActionTheme, THEME_TRANSITIONS


# P0-11 fix: role-based transition guards
TRANSITION_GUARDS = {
    ("detected", "confirmed"): ("admin", "analyst", "gt_reviewer"),
    ("confirmed", "content_generating"): ("admin", "content_editor"),
    ("confirmed", "dismissed"): ("admin", "analyst", "gt_reviewer"),
    ("content_generating", "content_ready"): ("admin", "content_editor"),
    ("content_ready", "approved"): ("admin", "legal_reviewer"),
    ("content_ready", "dismissed"): ("admin", "content_editor"),
    ("approved", "published_marked"): ("admin", "content_editor"),
    ("published_marked", "verification_pending"): ("admin",),
    ("verification_pending", "verified"): ("admin", "analyst"),
}


def can_transition(user_role: str, from_status: str, to_status: str) -> bool:
    """Check if the user role is allowed to trigger this state transition."""
    allowed_roles = TRANSITION_GUARDS.get((from_status, to_status), ())
    return user_role in allowed_roles


async def build_action_vm(brand, filters, user, db) -> dict:
    """Build view model for the Action workbench page."""
    return {}
