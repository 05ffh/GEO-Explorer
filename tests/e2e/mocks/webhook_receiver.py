"""Mock webhook receiver for E2E tests."""
import json
import logging

logger = logging.getLogger(__name__)

_received_webhooks: list[dict] = []


async def receive_webhook(request_body: dict, headers: dict) -> dict:
    """Mock: record webhook delivery instead of sending to external URL."""
    _received_webhooks.append({"body": request_body, "headers": dict(headers)})
    return {"status": "received", "mock": True}


def get_received_webhooks() -> list[dict]:
    return list(_received_webhooks)


def clear_webhooks():
    _received_webhooks.clear()
