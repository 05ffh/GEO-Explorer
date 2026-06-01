"""WordPress Mock Server — for testing WordPress adapter without a real WP instance (P2-4)."""
import json
import uuid
from urllib.parse import urlparse


class WPMockServer:
    """Lightweight in-process mock of WordPress REST API for testing."""

    def __init__(self, site_url: str = "https://example.com"):
        self.site_url = site_url.rstrip("/")
        self.posts: dict[str, dict] = {}
        self.pages: dict[str, dict] = {}
        self._users = {"admin": {"capabilities": {"create_posts": True, "edit_posts": True,
                                                    "create_pages": True, "edit_pages": True,
                                                    "publish_posts": False}}}
        self._rate_limited = False
        self._auth_fail = False
        self._server_error = False

    def set_auth_fail(self, fail: bool = True):
        self._auth_fail = fail

    def set_rate_limited(self, limited: bool = True):
        self._rate_limited = limited

    def set_server_error(self, error: bool = True):
        self._server_error = error

    async def handle_request(self, method: str, url: str, json_data: dict | None = None,
                              headers: dict | None = None) -> dict:
        """Handle a WordPress REST API request. Returns (status_code, response_body_dict)."""
        parsed = urlparse(url)
        path = parsed.path

        # Auth fail
        if self._auth_fail:
            return 401, {"code": "rest_cannot_access", "message": "Unauthorized"}

        # Rate limited
        if self._rate_limited:
            return 429, {"code": "rest_too_many_requests", "message": "Rate limited"}

        # Server error
        if self._server_error:
            return 500, {"code": "internal_error", "message": "Server error"}

        # GET /wp-json/wp/v2/types
        if path.endswith("/types") and method == "GET":
            return 200, {"post": {}, "page": {}}

        # GET /wp-json/wp/v2/users/me
        if path.endswith("/users/me") and method == "GET":
            return 200, {"id": 1, "name": "admin", "capabilities": self._users["admin"]["capabilities"]}

        # POST /wp-json/wp/v2/posts
        if path.endswith("/posts") and method == "POST":
            post_id = str(uuid.uuid4())
            post = {
                "id": post_id,
                "title": {"rendered": (json_data or {}).get("title", "")},
                "content": {"rendered": (json_data or {}).get("content", "")},
                "excerpt": {"rendered": (json_data or {}).get("excerpt", "")},
                "slug": (json_data or {}).get("slug", ""),
                "status": (json_data or {}).get("status", "draft"),
                "link": f"{self.site_url}/?p={post_id}",
                "_links": {"self": [{"href": f"{self.site_url}/wp-json/wp/v2/posts/{post_id}"}]},
            }
            self.posts[post_id] = post
            return 201, post

        # POST /wp-json/wp/v2/pages
        if path.endswith("/pages") and method == "POST":
            page_id = str(uuid.uuid4())
            page = {
                "id": page_id,
                "title": {"rendered": (json_data or {}).get("title", "")},
                "content": {"rendered": (json_data or {}).get("content", "")},
                "excerpt": {"rendered": (json_data or {}).get("excerpt", "")},
                "slug": (json_data or {}).get("slug", ""),
                "status": (json_data or {}).get("status", "draft"),
                "link": f"{self.site_url}/?page_id={page_id}",
                "_links": {"self": [{"href": f"{self.site_url}/wp-json/wp/v2/pages/{page_id}"}]},
            }
            self.pages[page_id] = page
            return 201, page

        # GET /wp-json/wp/v2/posts/{id}
        if "/posts/" in path and method == "GET":
            post_id = path.rstrip("/").split("/")[-1]
            if post_id in self.posts:
                return 200, self.posts[post_id]
            return 404, {"code": "rest_post_invalid_id", "message": "Not found"}

        return 404, {"code": "rest_no_route", "message": "No route"}


# Global singleton for test use
wp_mock = WPMockServer()
