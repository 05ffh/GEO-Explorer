"""GEO Explorer — Permission Map (permission-based, not role-based)."""

PERMISSIONS = {
    "gt.review":                  ["gt_reviewer", "admin", "owner"],
    "gt.promote":                 ["gt_reviewer", "admin", "owner"],
    "hallucination.review":       ["analyst", "gt_reviewer", "admin", "owner"],
    "action.transition":          ["analyst", "content_editor", "admin", "owner"],
    "content.approve.low":        ["content_editor", "legal_reviewer", "admin", "owner"],
    "content.approve.medium":     ["legal_reviewer", "admin", "owner"],
    "content.approve.high":       ["legal_reviewer", "admin", "owner"],
    "content.publish":            ["content_editor", "admin", "owner"],
    "report.export.summary":      ["analyst", "admin", "owner"],
    "report.export.full":         ["admin", "owner"],
    "audit.view.org":             ["admin", "owner"],
    "user.view":                  ["admin", "owner"],
    "user.invite":                ["admin", "owner"],
    "user.role_change":           ["admin", "owner"],
    "user.disable":               ["admin", "owner"],
    "user.remove":                ["admin", "owner"],
    "user.remove_admin":          ["owner"],
}


def has_permission(user_role: str, permission: str) -> bool:
    """Check if a user role has the given permission."""
    allowed = PERMISSIONS.get(permission, [])
    return user_role in allowed
