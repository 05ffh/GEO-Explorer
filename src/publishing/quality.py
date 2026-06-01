"""Publishing quality gates — pre-publish validation checks (P2-4)."""
import logging
from src.publishing.payload_builder import sanitize_html

logger = logging.getLogger(__name__)

FORBIDDEN_TERMS = {"未审核 GT", "API_KEY", "api_key", "内部 Prompt"}


async def check_publish_quality(content_package, publish_target, user, db) -> dict:
    """Run all pre-publish quality gates. Returns {passed: bool, failures: list, warnings: list}."""
    failures = []
    warnings = []

    # 1. ContentPackage must be approved
    if getattr(content_package, "status", "") != "approved":
        failures.append("ContentPackage 未审核通过")

    # 2. Quality status check
    cp_quality = getattr(content_package, "quality_status", "") or ""
    if cp_quality == "failed":
        failures.append("ContentPackage 质量检查失败")

    # 3. Check content for forbidden terms
    content_items = getattr(content_package, "content_items", []) or []
    for item in content_items:
        body = item.get("body", "")
        if isinstance(body, list) and body:
            body = str(body[0].get("body", body[0])) if isinstance(body[0], dict) else str(body[0])
        elif isinstance(body, dict):
            body = str(body.get("body", ""))
        body = str(body)
        for term in FORBIDDEN_TERMS:
            if term in body:
                failures.append(f"内容包含禁止词汇: {term}")

    # 4. Schema check
    schema_items = getattr(content_package, "schema_items", []) or []
    if not schema_items:
        warnings.append("缺少 Schema.org JSON-LD")

    # 5. PublishTarget status
    target_status = getattr(publish_target, "status", "")
    if target_status in ("archived",):
        failures.append("PublishTarget 已归档")
    health = getattr(publish_target, "health_status", "")
    if health in ("invalid", "paused"):
        failures.append(f"PublishTarget 健康状态异常: {health}")

    # 6. Credential check
    cred = getattr(publish_target, "credential_status", "")
    if cred == "invalid":
        failures.append("PublishTarget 凭据无效")

    # 7. HTML sanitization check
    for item in content_items:
        body = item.get("body", "")
        if isinstance(body, list) and body:
            body = str(body[0].get("body", body[0])) if isinstance(body[0], dict) else str(body[0])
        body = str(body)
        sanitized = sanitize_html(body)
        if sanitized != body:
            warnings.append("body_html 经 sanitization 处理")

    # 8. Auto-publish boundary
    auto_pub = getattr(publish_target, "auto_publish_on_approved", False)
    risk = getattr(content_package, "risk_level", "P2")
    if auto_pub and risk == "P0":
        failures.append("高风险(P0)内容不允许自动发布")

    passed = len(failures) == 0
    return {
        "passed": passed,
        "failures": failures,
        "warnings": warnings,
        "status": "passed" if passed else "failed",
    }
