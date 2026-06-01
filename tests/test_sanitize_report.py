"""Tests for report sanitization (P1-6)."""
from src.reports.sanitize_report import sanitize_report_context, _sanitize_string


class TestSanitizeString:
    def test_masks_api_key(self):
        assert _sanitize_string("sk-abcdefghijklmnop12345678") == "***REDACTED***"

    def test_masks_github_token(self):
        assert _sanitize_string("ghp_abcdefghijklmnopqrstuvwxyz1234567890") == "***REDACTED***"

    def test_masks_email(self):
        result = _sanitize_string("contact@example.com")
        assert "@" not in result or result == "***@***.***"

    def test_truncates_long_text(self):
        long_text = "A" * 600
        result = _sanitize_string(long_text)
        assert len(result) <= 503  # 500 + "..."

    def test_preserves_normal_text(self):
        text = "品牌表现正常"
        assert _sanitize_string(text) == text


class TestSanitizeContext:
    def test_removes_sensitive_keys(self):
        ctx = {
            "brand": {"name": "Test", "api_key": "sk-secret"},
            "kpis": [{"key": "sov", "api_token": "secret-token"}],
        }
        result = sanitize_report_context(ctx)
        assert result["brand"]["api_key"] == "***REDACTED***"
        assert result["kpis"][0]["api_token"] == "***REDACTED***"

    def test_preserves_normal_data(self):
        ctx = {"brand": {"name": "TestBrand", "industry": "SaaS"}}
        result = sanitize_report_context(ctx)
        assert result["brand"]["name"] == "TestBrand"

    def test_handles_empty(self):
        assert sanitize_report_context({}) == {}
        assert sanitize_report_context(None) == {}

    def test_nested_lists(self):
        ctx = {"items": [{"name": "a", "token": "sk-secret"}, {"name": "b"}]}
        result = sanitize_report_context(ctx)
        assert result["items"][0]["token"] == "***REDACTED***"
        assert result["items"][1]["name"] == "b"
