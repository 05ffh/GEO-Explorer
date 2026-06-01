"""WordPress REST API Adapter — draft creation, field mapping, schema insertion (P2-4 Phase 2)."""
import logging
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

WP_API_BASE = "/wp-json/wp/v2"
SCHEMA_SCRIPT_TEMPLATE = '\n<script type="application/ld+json">{}</script>'


class WordPressAdapter:
    """Publish Content Packages as WordPress drafts via REST API.

    Authentication: Application Password only (MVP).
    Default behavior: create draft (never auto-publish).
    """

    def __init__(self):
        self._client = None

    # ── Public API ─────────────────────────────────────────────────────────

    async def validate_config(self, target) -> dict:
        """Validate WordPress connection and permissions."""
        errors = []
        warnings = []
        cms_config = getattr(target, "cms_config", {}) or {}
        site_url = cms_config.get("wp_site_url", "")
        if not site_url:
            errors.append("缺少 wp_site_url")

        username = cms_config.get("wp_username", "")
        app_password = cms_config.get("wp_application_password", "")
        if not username or not app_password:
            errors.append("缺少 WordPress 凭据")

        if errors:
            return {"valid": False, "errors": errors, "warnings": warnings}

        try:
            auth = httpx.BasicAuth(username, app_password)
            async with httpx.AsyncClient(timeout=15.0, auth=auth) as client:
                # Check types endpoint
                resp = await client.get(urljoin(site_url, f"{WP_API_BASE}/types"))
                if resp.status_code == 401 or resp.status_code == 403:
                    return {"valid": False, "errors": ["凭据无效 (auth_failed)"],
                            "warnings": warnings}
                elif resp.status_code != 200:
                    return {"valid": False, "errors": [f"WordPress API 不可达 (HTTP {resp.status_code})"],
                            "warnings": warnings}

                # Check post types availability
                post_types = resp.json()
                supported = list(post_types.keys()) if isinstance(post_types, dict) else []

                # Check user capabilities
                users_resp = await client.get(urljoin(site_url, f"{WP_API_BASE}/users/me"))
                caps = {}
                if users_resp.status_code == 200:
                    caps = users_resp.json().get("capabilities", {})

                can_create_posts = "create_posts" in caps or "edit_posts" in caps
                can_create_pages = "create_pages" in caps or "edit_pages" in caps
                can_publish = "publish_posts" in caps

                warnings.append(f"wp_can_publish={can_publish} (never auto-publish)")
                if not can_create_posts and not can_create_pages:
                    errors.append("WordPress 用户缺少 create_posts/edit_posts 权限")

                return {
                    "valid": len(errors) == 0,
                    "errors": errors,
                    "warnings": warnings,
                    "wp_supported_post_types": supported,
                    "wp_can_create_posts": can_create_posts,
                    "wp_can_create_pages": can_create_pages,
                    "wp_can_publish": can_publish,
                }
        except httpx.ConnectError:
            return {"valid": False, "errors": ["无法连接到 WordPress 站点"]}
        except Exception as e:
            return {"valid": False, "errors": [f"验证失败: {str(e)[:200]}"]}

    async def create_draft(self, target, payload: dict) -> dict:
        """Create a WordPress draft from a publish payload."""
        cms_config = getattr(target, "cms_config", {}) or {}
        site_url = cms_config.get("wp_site_url", "")
        username = cms_config.get("wp_username", "")
        app_password = cms_config.get("wp_application_password", "")

        if not all([site_url, username, app_password]):
            return {"status": "failed", "error_category": "auth_failed",
                    "error_code": "MISSING_CREDENTIALS",
                    "error_message": "缺少 WordPress 凭据"}

        # Determine post type
        content_type = payload.get("content", {}).get("content_type", "")
        post_type = "pages" if "page" in content_type.lower() else "posts"
        endpoint = urljoin(site_url, f"{WP_API_BASE}/{post_type}")

        # Build WordPress post body
        content_body = payload.get("content", {}).get("body_html", "")
        schema_json_ld = payload.get("schema", {}).get("json_ld", {})

        # Insert schema as html_block at end of content
        import json
        if schema_json_ld and isinstance(schema_json_ld, dict):
            schema_script = SCHEMA_SCRIPT_TEMPLATE.format(
                json.dumps(schema_json_ld, ensure_ascii=False)
            )
            content_body += schema_script

        # Category/Tag mapping: id_only mode
        category_ids = cms_config.get("default_category_ids", []) or []
        tag_ids = cms_config.get("default_tag_ids", []) or []

        post_data = {
            "title": payload.get("content", {}).get("title", ""),
            "content": content_body,
            "excerpt": payload.get("content", {}).get("summary", ""),
            "slug": payload.get("content", {}).get("slug", ""),
            "status": "draft",  # Always draft, never publish
            "categories": category_ids,
            "tags": tag_ids,
        }

        # Determine if auto-publish is allowed
        auto_publish = payload.get("publishing", {}).get("auto_publish_allowed", False)
        target_auto = getattr(target, "auto_publish_on_approved", False)
        if auto_publish and target_auto:
            # Still default to draft; publish requires explicit admin override
            cms_config_override = getattr(target, "cms_config", {}) or {}
            if cms_config_override.get("allow_publish", False):
                post_data["status"] = "publish"

        try:
            auth = httpx.BasicAuth(username, app_password)
            async with httpx.AsyncClient(timeout=30.0, auth=auth) as client:
                resp = await client.post(endpoint, json=post_data)

                if resp.status_code == 401 or resp.status_code == 403:
                    return {"status": "failed", "error_category": "auth_failed",
                            "error_code": "WP_AUTH_FAILED",
                            "error_message": "WordPress 认证失败"}

                if resp.status_code == 400:
                    return {"status": "failed", "error_category": "invalid_payload",
                            "error_code": "WP_INVALID",
                            "error_message": f"WordPress 拒绝: {resp.text[:300]}"}

                if resp.status_code == 429:
                    return {"status": "failed", "error_category": "rate_limited",
                            "error_code": "WP_RATE_LIMITED", "retryable": True,
                            "error_message": "WordPress 限流"}

                if resp.status_code >= 500:
                    return {"status": "failed", "error_category": "server_error",
                            "error_code": f"WP_HTTP_{resp.status_code}", "retryable": True,
                            "error_message": f"WordPress 服务器错误 (HTTP {resp.status_code})"}

                if 200 <= resp.status_code < 300:
                    result = resp.json()
                    wp_id = str(result.get("id", ""))
                    wp_link = result.get("link", "")
                    wp_edit_link = result.get("_links", {}).get("wp:action-publish", [{}])[0].get("href", "") if False else ""
                    # Get edit link from _links
                    edit_links = []
                    if "_links" in result and "self" in result["_links"]:
                        edit_link_info = result["_links"]["self"][0] if result["_links"]["self"] else {}
                        edit_links.append(edit_link_info.get("href", ""))

                    return {
                        "status": "success",
                        "external_id": wp_id,
                        "external_edit_url": f"{site_url}/wp-admin/post.php?post={wp_id}&action=edit",
                        "external_preview_url": result.get("link", ""),
                        "external_public_url": result.get("link", ""),
                        "external_status": result.get("status", "draft"),
                    }

                return {"status": "failed", "error_category": "unknown_error",
                        "error_code": f"WP_HTTP_{resp.status_code}",
                        "error_message": f"意外响应 (HTTP {resp.status_code})"}

        except httpx.TimeoutException:
            return {"status": "failed", "error_category": "timeout",
                    "error_code": "WP_TIMEOUT", "retryable": True,
                    "error_message": "WordPress 请求超时"}
        except httpx.ConnectError:
            return {"status": "failed", "error_category": "target_unreachable",
                    "error_code": "WP_UNREACHABLE", "retryable": True,
                    "error_message": "无法连接 WordPress 站点"}
        except Exception as e:
            return {"status": "failed", "error_category": "unknown_error",
                    "error_code": "WP_UNKNOWN",
                    "error_message": str(e)[:300]}

    async def update_draft(self, target, external_id: str, payload: dict) -> dict:
        """Update an existing WordPress draft."""
        cms_config = getattr(target, "cms_config", {}) or {}
        site_url = cms_config.get("wp_site_url", "")
        username = cms_config.get("wp_username", "")
        app_password = cms_config.get("wp_application_password", "")

        if not all([site_url, username, app_password]):
            return {"status": "failed", "error_category": "auth_failed"}

        content_type = payload.get("content", {}).get("content_type", "")
        post_type = "pages" if "page" in content_type.lower() else "posts"
        endpoint = urljoin(site_url, f"{WP_API_BASE}/{post_type}/{external_id}")

        content_body = payload.get("content", {}).get("body_html", "")
        schema_json_ld = payload.get("schema", {}).get("json_ld", {})

        # Append schema (but don't duplicate if already present)
        import json
        if schema_json_ld and isinstance(schema_json_ld, dict):
            schema_script = SCHEMA_SCRIPT_TEMPLATE.format(
                json.dumps(schema_json_ld, ensure_ascii=False)
            )
        else:
            schema_script = ""

        post_data = {
            "title": payload.get("content", {}).get("title", ""),
            "content": content_body,
            "excerpt": payload.get("content", {}).get("summary", ""),
            "slug": payload.get("content", {}).get("slug", ""),
            "status": "draft",
        }

        try:
            auth = httpx.BasicAuth(username, app_password)
            async with httpx.AsyncClient(timeout=30.0, auth=auth) as client:
                resp = await client.post(endpoint, json=post_data)
                if 200 <= resp.status_code < 300:
                    result = resp.json()
                    return {
                        "status": "success",
                        "external_id": str(result.get("id", external_id)),
                        "external_edit_url": f"{site_url}/wp-admin/post.php?post={result.get('id', external_id)}&action=edit",
                        "external_public_url": result.get("link", ""),
                        "external_status": result.get("status", "draft"),
                    }
                return {"status": "failed", "error_category": "server_error",
                        "error_code": f"WP_HTTP_{resp.status_code}",
                        "error_message": f"更新失败 (HTTP {resp.status_code})"}
        except Exception as e:
            return {"status": "failed", "error_category": "unknown_error",
                    "error_message": str(e)[:300]}

    async def get_status(self, target, external_id: str) -> dict:
        """Get current status of a WordPress post."""
        cms_config = getattr(target, "cms_config", {}) or {}
        site_url = cms_config.get("wp_site_url", "")
        username = cms_config.get("wp_username", "")
        app_password = cms_config.get("wp_application_password", "")

        if not all([site_url, username, app_password]):
            return {"status": "error", "error_category": "auth_failed"}

        try:
            auth = httpx.BasicAuth(username, app_password)
            async with httpx.AsyncClient(timeout=15.0, auth=auth) as client:
                resp = await client.get(urljoin(site_url, f"{WP_API_BASE}/posts/{external_id}"))
                if resp.status_code == 200:
                    result = resp.json()
                    return {
                        "external_id": str(result.get("id", "")),
                        "external_status": result.get("status", ""),
                        "external_public_url": result.get("link", ""),
                    }
                return {"status": "error", "error_code": f"WP_HTTP_{resp.status_code}"}
        except Exception as e:
            return {"status": "error", "error_message": str(e)[:200]}


# Singleton
wordpress_adapter = WordPressAdapter()
