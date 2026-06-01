"""CMS Adapter Protocol — defines the interface for CMS adapters (P2-4)."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class CMSAdapter(Protocol):
    """Protocol for CMS publishing adapters (WordPress, Webflow, Custom REST)."""

    async def validate_config(self, target) -> dict:
        """Validate the target configuration. Returns {valid: bool, errors: list}."""
        ...

    async def create_draft(self, target, payload: dict) -> dict:
        """Create a draft in the CMS. Returns {status, external_id, external_urls}."""
        ...

    async def update_draft(self, target, external_id: str, payload: dict) -> dict:
        """Update an existing draft. Returns {status, external_id, external_urls}."""
        ...

    async def get_status(self, target, external_id: str) -> dict:
        """Get the current status of a published item. Returns {status, external_urls}."""
        ...


class BaseCMSAdapter:
    """Base class with common functionality for CMS adapters."""

    async def validate_config(self, target) -> dict:
        return {"valid": True, "errors": []}

    async def create_draft(self, target, payload: dict) -> dict:
        raise NotImplementedError

    async def update_draft(self, target, external_id: str, payload: dict) -> dict:
        raise NotImplementedError

    async def get_status(self, target, external_id: str) -> dict:
        raise NotImplementedError
