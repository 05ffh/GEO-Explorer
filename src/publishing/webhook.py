"""Webhook delivery — send + retry + attempt logging (P2-4)."""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.publishing.security import (compute_hmac_signature, redact_publish_payload,
                                      redact_response_body, validate_webhook_url)
from src.publishing.events import write_publish_event
from src.publishing.models import PublishAttempt as PublishAttemptModel

logger = logging.getLogger(__name__)

# Retry policy
RETRY_SCHEDULE_MINUTES = [5, 15, 30]
MAX_RETRIES = 3

# Error categories that are retryable
RETRYABLE_CATEGORIES = {"target_unreachable", "timeout", "rate_limited", "server_error"}


def classify_webhook_error(status_code: int | None, error_text: str = "") -> dict:
    """Classify a webhook response into error_category and retryable flag."""
    if status_code is None:
        return {"error_category": "target_unreachable", "retryable": True,
                "error_code": "CONNECTION_FAILED"}

    if status_code in (401, 403):
        return {"error_category": "auth_failed", "retryable": False, "error_code": f"HTTP_{status_code}"}
    if status_code == 429:
        return {"error_category": "rate_limited", "retryable": True, "error_code": "RATE_LIMITED"}
    if status_code == 400:
        return {"error_category": "invalid_payload", "retryable": False, "error_code": f"HTTP_{status_code}"}
    if status_code == 422:
        return {"error_category": "invalid_payload", "retryable": False, "error_code": f"HTTP_{status_code}"}
    if 500 <= status_code < 600:
        return {"error_category": "server_error", "retryable": True, "error_code": f"HTTP_{status_code}"}
    if status_code == 408:
        return {"error_category": "timeout", "retryable": True, "error_code": "TIMEOUT"}

    return {"error_category": "unknown_error", "retryable": False, "error_code": f"HTTP_{status_code}"}


async def deliver_webhook(db: AsyncSession, *, publish_request_id, publish_target_id,
                           organization_id, brand_id, content_package_id,
                           publish_batch_id, payload: dict, webhook_url: str,
                           webhook_secret: str, attempt_no: int = 1,
                           task_state_id: str | None = None) -> dict:
    """Deliver a payload to a webhook URL. Creates PublishAttempt, handles retry scheduling."""

    # Validate URL first
    valid, err = validate_webhook_url(webhook_url)
    if not valid:
        return await _record_attempt(db, publish_request_id, publish_target_id,
                                      organization_id, brand_id,
                                      content_package_id, publish_batch_id,
                                      payload, attempt_no, status="failed",
                                      error_category="ssrf_blocked",
                                      error_code="SSRF_BLOCKED",
                                      error_message=err,
                                      retryable=False,
                                      task_state_id=task_state_id)

    # Build request
    now = datetime.now(timezone.utc)
    timestamp = str(int(now.timestamp()))
    body = json.dumps(payload, ensure_ascii=False).encode()
    payload_hash = hashlib.sha256(body).hexdigest()
    signature = compute_hmac_signature(body, webhook_secret, timestamp)

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-GEO-Event": "content_package.ready_for_publish",
        "X-GEO-Event-ID": payload.get("event_id", str(uuid.uuid4())),
        "X-GEO-Timestamp": timestamp,
        "X-GEO-Signature": signature,
        "X-GEO-Payload-Version": payload.get("version", "2026-05"),
    }

    # Send
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(webhook_url, content=body, headers=headers)
            status_code = resp.status_code
            response_text = resp.text[:1000]
    except httpx.TimeoutException:
        return await _record_attempt(db, publish_request_id, publish_target_id,
                                      organization_id, brand_id,
                                      content_package_id, publish_batch_id,
                                      payload, attempt_no, status="failed",
                                      error_category="timeout",
                                      error_code="TIMEOUT",
                                      error_message="请求超时 (30s)",
                                      retryable=True,
                                      task_state_id=task_state_id)
    except httpx.ConnectError as e:
        return await _record_attempt(db, publish_request_id, publish_target_id,
                                      organization_id, brand_id,
                                      content_package_id, publish_batch_id,
                                      payload, attempt_no, status="failed",
                                      error_category="target_unreachable",
                                      error_code="CONNECTION_FAILED",
                                      error_message=str(e)[:500],
                                      retryable=True,
                                      task_state_id=task_state_id)
    except Exception as e:
        return await _record_attempt(db, publish_request_id, publish_target_id,
                                      organization_id, brand_id,
                                      content_package_id, publish_batch_id,
                                      payload, attempt_no, status="failed",
                                      error_category="unknown_error",
                                      error_code="UNKNOWN",
                                      error_message=str(e)[:500],
                                      retryable=False,
                                      task_state_id=task_state_id)

    # Classify response
    classification = classify_webhook_error(status_code, response_text)
    is_success = 200 <= status_code < 300

    return await _record_attempt(db, publish_request_id, publish_target_id,
                                  organization_id, brand_id,
                                  content_package_id, publish_batch_id,
                                  payload, attempt_no,
                                  status="success" if is_success else "failed",
                                  response_status_code=status_code,
                                  response_body=response_text,
                                  error_category=classification["error_category"] if not is_success else None,
                                  error_code=classification["error_code"] if not is_success else None,
                                  retryable=classification["retryable"] if not is_success else False,
                                  task_state_id=task_state_id)


async def schedule_retry(db: AsyncSession, attempt_result: dict, attempt_no: int) -> dict | None:
    """Determine if a retry should be scheduled. Returns next_retry_at or None."""
    if not attempt_result.get("retryable"):
        return None
    if attempt_no >= MAX_RETRIES:
        return None
    delay_min = RETRY_SCHEDULE_MINUTES[min(attempt_no, len(RETRY_SCHEDULE_MINUTES) - 1)]
    return {"next_retry_at": datetime.now(timezone.utc).timestamp() + delay_min * 60,
            "delay_minutes": delay_min}


# ── Internal ──────────────────────────────────────────────────────────────────

async def _record_attempt(db: AsyncSession, request_id, target_id, org_id, brand_id,
                           cp_id, batch_id, payload, attempt_no, status,
                           response_status_code=None, response_body=None,
                           error_category=None, error_code=None, error_message=None,
                           retryable=False, task_state_id=None) -> dict:
    """Create a PublishAttempt record and write a PublishEvent."""
    now = datetime.now(timezone.utc)
    attempt_id = uuid.uuid4()
    payload_hash = payload.get("payload_hash", "")
    if isinstance(payload, dict) and "payload_hash" not in payload:
        payload_hash = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

    # Determine next_retry
    next_retry = None
    if status == "failed" and retryable and attempt_no < MAX_RETRIES:
        delay_min = RETRY_SCHEDULE_MINUTES[min(attempt_no, len(RETRY_SCHEDULE_MINUTES) - 1)]
        next_retry = datetime.now(timezone.utc)
        # datetime addition in SQL handles this

    safe_response = redact_response_body(response_body or "") if response_body else None

    await db.execute(text("""
        INSERT INTO publish_attempts (id, publish_request_id, publish_target_id,
            attempt_no, channel, status, request_payload_hash,
            response_status_code, response_body_summary,
            task_state_id, error_code, error_category, retryable,
            error_message, sent_at, next_retry_at, created_at, updated_at)
        VALUES (:id, :rid, :tid, :ano, 'webhook', :status, :hash,
            :resp_code, :resp_body, :tsid, :err_code, :err_cat, :retryable,
            :err_msg, :now, :next_retry, :now, :now)
    """), {
        "id": attempt_id, "rid": request_id, "tid": target_id, "ano": attempt_no,
        "status": status, "hash": payload_hash,
        "resp_code": response_status_code, "resp_body": safe_response,
        "tsid": task_state_id, "err_code": error_code, "err_cat": error_category,
        "retryable": retryable, "err_msg": (error_message or "")[:1000],
        "now": now, "next_retry": None,
    })

    await write_publish_event(db, organization_id=org_id, brand_id=brand_id,
                               content_package_id=cp_id, publish_batch_id=batch_id,
                               publish_request_id=request_id,
                               publish_attempt_id=attempt_id,
                               event_type="publish_attempt_succeeded" if status == "success" else "publish_attempt_failed",
                               message=f"Attempt {attempt_no} {status}",
                               metadata_json={"attempt_no": attempt_no, "status": status,
                                              "error_category": error_category,
                                              "error_code": error_code})
    await db.flush()

    return {
        "attempt_id": str(attempt_id), "attempt_no": attempt_no, "status": status,
        "error_category": error_category, "error_code": error_code,
        "retryable": retryable, "response_status_code": response_status_code,
    }
