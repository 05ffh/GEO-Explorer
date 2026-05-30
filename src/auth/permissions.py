"""GEO Explorer — Dual-Layer Permission System.

Layer 1 — Platform Roles (system_owner / system_admin / system_operator):
  Control access to platform-wide operations (manage orgs, config, billing).

Layer 2 — Organization Roles (owner / admin / analyst / ...):
  Control access to operations within a single organization.

system_owner has implicit ALL permissions.

Organization-level permissions need org membership check.
"""

# ---- Platform-Level Permissions ----
# system_owner has ALL; system_admin/system_operator have scoped access.
PLATFORM_PERMISSIONS = {
    "platform.organization.create":   ["system_owner"],
    "platform.organization.disable":  ["system_owner"],
    "platform.organization.delete":   ["system_owner"],
    "platform.user.manage_all":       ["system_owner", "system_admin"],
    "platform.config.manage":         ["system_owner", "system_admin"],
    "platform.api_key.manage":        ["system_owner"],
    "platform.task_queue.manage":     ["system_owner", "system_admin"],
    "platform.audit.view_all":        ["system_owner", "system_admin"],
    "platform.security_event.view":   ["system_owner", "system_admin"],
    "platform.support_access":        ["system_owner", "system_admin"],
    "platform.system_health.view":    ["system_owner", "system_admin", "system_operator"],
    "platform.billing.manage":        ["system_owner"],
}

# ---- Organization-Level Permissions ----
ORG_PERMISSIONS = {
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


def has_platform_permission(platform_role: str | None, permission: str) -> bool:
    """Check platform-level permission. system_owner has all."""
    if not platform_role:
        return False
    if platform_role == "system_owner":
        return True
    allowed = PLATFORM_PERMISSIONS.get(permission, [])
    return platform_role in allowed


def has_org_permission(org_role: str | None, permission: str) -> bool:
    """Check organization-level permission."""
    if not org_role:
        return False
    allowed = ORG_PERMISSIONS.get(permission, [])
    return org_role in allowed


def has_permission(user_platform_role: str | None, user_org_role: str | None,
                   permission: str) -> bool:
    """Unified permission check — platform overrides org.

    system_owner has implicit ALL permissions (platform + org).
    For org permissions, system_admin/system_operator also need explicit grant.
    """
    # Platform-level perms: only platform roles matter
    if permission.startswith("platform."):
        return has_platform_permission(user_platform_role, permission)

    # Org-level perms: system_owner has all, others check org role
    if user_platform_role == "system_owner":
        return True
    return has_org_permission(user_org_role, permission)
