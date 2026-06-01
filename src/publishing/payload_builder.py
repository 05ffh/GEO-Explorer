"""Publish Payload Builder — constructs standardized publish payloads with versioning, validation, and sanitization (P2-4)."""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from html import escape

logger = logging.getLogger(__name__)

PAYLOAD_VERSION = "2026-05"

ALLOWED_HTML_TAGS = {"p", "br", "strong", "em", "b", "i", "a", "ul", "ol", "li",
                     "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "code",
                     "table", "thead", "tbody", "tr", "th", "td", "hr", "img"}

FORBIDDEN_HTML_TAGS = {"script", "iframe", "object", "embed", "form", "input",
                       "button", "link", "style", "meta", "noscript"}

ASSET_TYPE_ALLOWLIST = {"image", "document", "video_embed"}


def build_publish_payload(content_package: dict, publish_target: dict,
                          publish_request_id: str, publish_action: str = "create",
                          version: str | None = None) -> dict:
    """Build a standard publish payload from a ContentPackage and PublishTarget."""
    v = version or publish_target.get("payload_version", PAYLOAD_VERSION)
    now = datetime.now(timezone.utc)
    event_id = str(uuid.uuid4())

    org_id = content_package.get("organization_id", "")
    brand_id = content_package.get("brand_id", "")
    cp_id = content_package.get("id", "")

    content_items = content_package.get("content_items", [])
    schema_items = content_package.get("schema_items", [])
    checklist = content_package.get("publishing_checklist", [])

    first_item = content_items[0] if content_items else {}
    body_md = first_item.get("body", "")
    if isinstance(body_md, list) and body_md:
        body_md = body_md[0].get("body", body_md[0]) if isinstance(body_md[0], dict) else str(body_md[0])
    elif isinstance(body_md, dict):
        body_md = body_md.get("body", "")
    body_md = str(body_md)

    body_html = _markdown_to_html(body_md)
    body_html = sanitize_html(body_html)

    first_schema = schema_items[0] if schema_items else {}
    schema_type = first_schema.get("@type", "WebPage")

    title = first_item.get("theme", "") or first_item.get("title", "")
    content_type = first_item.get("content_type", "faq_page")
    recommended_path = first_item.get("recommended_path", "")

    risk_level = content_package.get("risk_level", "P2")
    auto_publish = publish_target.get("auto_publish_on_approved", False)

    callback_token = str(uuid.uuid4())
    callback_url = ""  # populated from config

    payload = {
        "event": "content_package.ready_for_publish",
        "event_id": event_id,
        "version": v,
        "organization_id": str(org_id),
        "brand_id": str(brand_id),
        "content_package_id": str(cp_id),
        "publish_request_id": str(publish_request_id),
        "publish_action": publish_action,
        "content": {
            "title": title,
            "slug": _slugify(title),
            "summary": first_item.get("summary", ""),
            "body_markdown": body_md,
            "body_html": body_html,
            "language": "zh-CN",
            "content_type": content_type,
            "recommended_path": recommended_path,
            "tags": first_item.get("tags", []) or [],
            "categories": first_item.get("categories", []) or [],
        },
        "schema": {
            "type": schema_type,
            "json_ld": first_schema,
        },
        "assets": _build_assets(first_item.get("assets", [])),
        "assets_policy": {
            "mode": "external_reference",
            "media_upload_supported": False,
        },
        "geo_context": {
            "target_kpis": first_item.get("target_kpis", []) or [],
            "target_issues": first_item.get("target_issues", []) or [],
            "industry_template": content_package.get("industry_template", ""),
            "risk_level": risk_level,
            "evidence_summary": content_package.get("fact_check_report", {}).get("summary", ""),
        },
        "publishing": {
            "review_required": content_package.get("review_required", True),
            "suggested_status": "draft",
            "auto_publish_allowed": auto_publish,
            "expires_at": "",
        },
        "callback": {
            "status_callback_url": callback_url,
            "callback_token": callback_token,
        },
    }

    payload_hash = compute_payload_hash(payload)
    validate_publish_payload(payload, version=v)

    return payload, payload_hash, callback_token


def compute_payload_hash(payload: dict) -> str:
    """Stable SHA256 hash of a publish payload (excluding volatile fields)."""
    stable = {
        k: v for k, v in payload.items()
        if k not in ("event_id", "callback")
    }
    raw = _json_canonical(stable)
    return hashlib.sha256(raw.encode()).hexdigest()


def validate_publish_payload(payload: dict, version: str | None = None) -> list[str]:
    """Validate a publish payload. Returns list of errors (empty = valid)."""
    errors = []
    required = ["event", "event_id", "version", "content_package_id", "publish_request_id",
                "content", "schema", "geo_context", "publishing", "callback"]
    for key in required:
        if key not in payload:
            errors.append(f"缺少必填字段: {key}")

    content = payload.get("content", {})
    if not content.get("title"):
        errors.append("content.title 不能为空")
    if not content.get("body_html"):
        errors.append("content.body_html 不能为空")

    geo = payload.get("geo_context", {})
    if not geo.get("target_kpis"):
        errors.append("geo_context.target_kpis 不能为空")

    pub = payload.get("publishing", {})
    if "auto_publish_allowed" not in pub:
        errors.append("publishing.auto_publish_allowed 必须明确")

    cb = payload.get("callback", {})
    if not cb.get("callback_token"):
        errors.append("callback.callback_token 不能为空")

    # Forbidden content check
    forbidden = _check_forbidden_content(payload)
    errors.extend(forbidden)

    return errors


def sanitize_html(html: str) -> str:
    """Remove disallowed tags from HTML body."""
    import re
    if not html:
        return ""
    for tag in FORBIDDEN_HTML_TAGS:
        html = re.sub(rf'<\s*{tag}[^>]*>.*?<\s*/\s*{tag}\s*>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(rf'<\s*{tag}[^>]*/?\s*>', '', html, flags=re.IGNORECASE)
    # Strip javascript: protocol
    html = re.sub(r'href\s*=\s*["\']javascript:', 'href="', html, flags=re.IGNORECASE)
    return html


# ── Internal helpers ──────────────────────────────────────────────────────────

def _markdown_to_html(md: str) -> str:
    """Simple markdown-to-HTML conversion for publish payloads."""
    import re
    if not md:
        return ""
    html = md
    # Headers
    html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
    html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    # Bold/italic
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    # Links
    html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)
    # Unordered lists (simple single-line items)
    html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.MULTILINE)
    # Paragraphs (blank-line separated)
    paragraphs = re.split(r'\n\n+', html)
    wrapped = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if not re.match(r'^<(h[1-6]|ul|ol|li|blockquote|pre|table)', p):
            p = f"<p>{p}</p>"
        wrapped.append(p)
    html = "\n".join(wrapped)
    return html


def _slugify(text: str) -> str:
    """Generate a URL slug from text."""
    import re
    if not text:
        return ""
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')


def _build_assets(assets: list | None) -> list:
    """Validate and sanitize asset entries."""
    if not assets:
        return []
    result = []
    for a in assets:
        if not isinstance(a, dict):
            continue
        asset_type = a.get("type", "")
        if asset_type not in ASSET_TYPE_ALLOWLIST:
            continue
        url = a.get("url", "")
        if not url.startswith("https://"):
            continue
        entry = {
            "asset_id": a.get("asset_id", str(uuid.uuid4())),
            "type": asset_type,
            "url": url,
            "alt": a.get("alt", "") if asset_type == "image" else a.get("alt", ""),
            "usage": a.get("usage", ""),
        }
        if asset_type == "image" and not entry["alt"]:
            continue  # image must have alt
        result.append(entry)
    return result


def _check_forbidden_content(payload: dict) -> list[str]:
    """Check for forbidden terms in payload content."""
    errors = []
    body = payload.get("content", {}).get("body_html", "")
    if "未审核 GT" in body:
        errors.append("内容包含未审核的 Ground Truth")
    if "API_KEY" in body or "api_key" in body:
        errors.append("内容包含 API Key 敏感信息")
    return errors


def _json_canonical(obj) -> str:
    """Minimal canonical JSON serialization for hashing."""
    import json
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
