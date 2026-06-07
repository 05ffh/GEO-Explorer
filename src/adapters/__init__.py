"""Platform adapter registry with dependency injection support.

Production: uses DEFAULT_ADAPTERS (classes, instantiated per-query).
Testing: inject a custom adapter_registry dict via run_collection().
"""

from src.adapters.base import PlatformAdapter, OpenAICompatibleAdapter, AIResponse, Citation
from src.adapters.deepseek import DeepSeekAdapter
from src.adapters.kimi import KimiAdapter
from src.adapters.doubao import DoubaoAdapter
from src.adapters.wenxin import WenxinAdapter
from src.adapters.mock import MockAdapter, MockPlatformAdapter

# ── Default registry (production) ───────────────────────────────────────────
# Maps platform name → adapter CLASS (instantiated per query by CollectorEngine)

DEFAULT_ADAPTERS: dict[str, type] = {
    "deepseek": DeepSeekAdapter,
    "kimi": KimiAdapter,
    "doubao": DoubaoAdapter,
    "wenxin": WenxinAdapter,
}

# Legacy alias — prefer passing adapter_registry explicitly
ADAPTERS = DEFAULT_ADAPTERS


def get_adapter(platform: str, registry: dict | None = None):
    """Get an adapter instance for a platform.

    Args:
        platform: platform name (deepseek, kimi, doubao, wenxin)
        registry: optional adapter dict (classes or instances). Falls back to DEFAULT_ADAPTERS.
    """
    reg = registry or DEFAULT_ADAPTERS
    factory = reg.get(platform)
    if factory is None:
        from src.config import settings
        if getattr(settings, 'disable_real_http_in_tests', False):
            raise AdapterNotFoundError(
                f"No adapter registered for platform '{platform}' — "
                f"DISABLE_REAL_HTTP_IN_TESTS is active, refusing to fallback"
            )
        raise AdapterNotFoundError(f"No adapter registered for platform: {platform}")
    # If factory is a class → instantiate; if callable → call it; else return as-is
    if isinstance(factory, type):
        return factory()
    if callable(factory):
        return factory()
    return factory


class AdapterNotFoundError(RuntimeError):
    """Raised when a platform has no registered adapter."""
    pass


__all__ = [
    "PlatformAdapter", "OpenAICompatibleAdapter", "AIResponse", "Citation",
    "DeepSeekAdapter", "KimiAdapter", "DoubaoAdapter", "WenxinAdapter",
    "MockAdapter", "MockPlatformAdapter",
    "DEFAULT_ADAPTERS", "ADAPTERS", "get_adapter", "AdapterNotFoundError",
]
