"""GEO Explorer — Audit Log Service.

Adds audit records to the current transaction without committing.
Callers are responsible for db.commit() after all operations.
"""

SENSITIVE_FIELDS = {"api_key", "token", "password", "secret", "authorization",
                    "cookie", "access_token", "refresh_token", "private_note"}


def sanitize_payload(payload: dict) -> dict:
    """Mask sensitive fields in audit payloads."""
    if not payload:
        return {}
    result = {}
    for k, v in payload.items():
        if k.lower() in SENSITIVE_FIELDS:
            result[k] = "***REDACTED***"
        elif isinstance(v, dict):
            result[k] = sanitize_payload(v)
        elif isinstance(v, list):
            result[k] = [sanitize_payload(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


async def add_audit_log(db, user, action: str, target_type: str, target_id: str,
                        before: dict | None = None,
                        after: dict | None = None,
                        detail: dict | None = None,
                        reason: str = "",
                        result: str = "success",
                        error_code: str = "",
                        error_message: str = "",
                        brand_id: str | None = None,
                        request=None) -> None:
    """Add an audit log entry to the current DB session.

    IMPORTANT: Does NOT call db.commit() — the caller must commit.
    This keeps audit and business changes in the same transaction (P0-2).
    """
    if db is None:
        return
    from src.models.audit_log import AuditLog

    req_id = ""
    ip = ""
    ua = ""
    if request:
        req_id = getattr(getattr(request, "state", None), "request_id", "")
        if hasattr(request, "client") and request.client:
            ip = request.client.host or ""
        ua = request.headers.get("user-agent", "") if hasattr(request, "headers") else ""

    log_entry = AuditLog(
        organization_id=user.organization_id if user else None,
        brand_id=brand_id,
        user_id=user.id if user else None,
        user_name=user.name or "" if user else "",
        user_role=user.role or "" if user else "",
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        before_json=sanitize_payload(before or {}),
        after_json=sanitize_payload(after or {}),
        detail=sanitize_payload(detail or {}),
        reason=reason,
        result=result,
        error_code=error_code,
        error_message=error_message,
        request_id=req_id,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(log_entry)
