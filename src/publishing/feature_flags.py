"""Publishing feature flags — gradual rollout control (P2-4)."""

# Feature flag defaults (all off for safe rollout)
FEATURE_FLAGS = {
    "publishing_webhook_enabled": False,
    "publishing_wordpress_enabled": False,
    "publishing_auto_publish_enabled": False,
    "publishing_batch_enabled": False,
    "publishing_assets_enabled": False,
}

# Overrides per organization
_org_overrides: dict = {}


def is_enabled(flag: str, org_id: str | None = None) -> bool:
    """Check if a publishing feature flag is enabled."""
    if org_id and org_id in _org_overrides:
        org_flags = _org_overrides[org_id]
        if flag in org_flags:
            return org_flags[flag]
    return FEATURE_FLAGS.get(flag, False)


def enable_for_org(flag: str, org_id: str):
    """Enable a feature flag for a specific organization."""
    if org_id not in _org_overrides:
        _org_overrides[org_id] = {}
    _org_overrides[org_id][flag] = True


def disable_for_org(flag: str, org_id: str):
    """Disable a feature flag for a specific organization."""
    if org_id in _org_overrides:
        _org_overrides[org_id][flag] = False


def set_global(flag: str, enabled: bool):
    """Set a global feature flag (system_admin only)."""
    if flag in FEATURE_FLAGS:
        FEATURE_FLAGS[flag] = enabled
