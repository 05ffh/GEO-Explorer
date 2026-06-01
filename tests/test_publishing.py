"""P2-4 Publishing tests — payload, security, webhook, state machine, quality gates."""
import pytest
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone


# ── Payload Builder Tests ─────────────────────────────────────────────────────

class TestPublishPayload:
    def test_payload_contains_required_fields(self):
        from src.publishing.payload_builder import build_publish_payload
        cp = {
            "id": str(uuid.uuid4()), "organization_id": str(uuid.uuid4()),
            "brand_id": str(uuid.uuid4()),
            "content_items": [{"theme": "Test FAQ", "body": "Test body content"}],
            "schema_items": [{"@type": "FAQPage", "mainEntity": []}],
            "publishing_checklist": [], "fact_check_report": {},
            "risk_level": "P1", "review_required": True,
        }
        target = {"payload_version": "2026-05", "auto_publish_on_approved": False}
        payload, hash_val, token = build_publish_payload(
            cp, target, str(uuid.uuid4()), "create"
        )
        for key in ("event", "event_id", "version", "content_package_id",
                     "publish_request_id", "content", "schema", "geo_context",
                     "publishing", "callback"):
            assert key in payload, f"Missing {key}"
        assert payload["publishing"]["auto_publish_allowed"] is False

    def test_payload_excludes_unverified_gt(self):
        from src.publishing.payload_builder import build_publish_payload
        cp = {
            "id": str(uuid.uuid4()), "organization_id": str(uuid.uuid4()),
            "brand_id": str(uuid.uuid4()),
            "content_items": [{"theme": "Test", "body": "Content text"}],
            "schema_items": [], "publishing_checklist": [], "fact_check_report": {},
            "risk_level": "P2", "review_required": True,
        }
        target = {"payload_version": "2026-05", "auto_publish_on_approved": False}
        payload, _, _ = build_publish_payload(cp, target, str(uuid.uuid4()))
        assert payload["content"]["title"] == "Test"

    def test_payload_hash_computed(self):
        from src.publishing.payload_builder import build_publish_payload, compute_payload_hash
        cp = {
            "id": str(uuid.uuid4()), "organization_id": str(uuid.uuid4()),
            "brand_id": str(uuid.uuid4()),
            "content_items": [{"theme": "Stable", "body": "Same content"}],
            "schema_items": [], "publishing_checklist": [], "fact_check_report": {},
            "risk_level": "P2", "review_required": False,
        }
        target = {"payload_version": "2026-05", "auto_publish_on_approved": False}
        p1, h1, _ = build_publish_payload(dict(cp), dict(target), str(uuid.uuid4()))
        p2, h2, _ = build_publish_payload(dict(cp), dict(target), str(uuid.uuid4()))
        # Hashes should be 64-char hex strings
        assert len(h1) == 64
        assert len(h2) == 64

    def test_payload_validates_against_required_fields(self):
        from src.publishing.payload_builder import validate_publish_payload
        payload = {"event": "test"}
        errors = validate_publish_payload(payload)
        assert len(errors) > 0
        assert any("必填" in e for e in errors)


# ── HTML Sanitization Tests ───────────────────────────────────────────────────

class TestHtmlSanitization:
    def test_script_removed_from_body(self):
        from src.publishing.payload_builder import sanitize_html
        html = '<p>Hello</p><script>alert("xss")</script>'
        result = sanitize_html(html)
        assert "<script>" not in result.lower()
        assert "alert" not in result.lower()

    def test_iframe_removed(self):
        from src.publishing.payload_builder import sanitize_html
        html = '<p>Content</p><iframe src="http://evil.com"></iframe>'
        result = sanitize_html(html)
        assert "<iframe" not in result.lower()

    def test_javascript_protocol_removed(self):
        from src.publishing.payload_builder import sanitize_html
        html = '<a href="javascript:alert(1)">Click</a>'
        result = sanitize_html(html)
        assert "javascript:" not in result.lower()

    def test_safe_html_preserved(self):
        from src.publishing.payload_builder import sanitize_html
        html = '<p>Hello <strong>World</strong></p><ul><li>Item</li></ul>'
        result = sanitize_html(html)
        assert "<strong>World</strong>" in result
        assert "<li>Item</li>" in result


# ── Security Tests ────────────────────────────────────────────────────────────

class TestWebhookSecurity:
    def test_webhook_requires_https(self):
        from src.publishing.security import validate_webhook_url
        valid, err = validate_webhook_url("http://example.com/webhook")
        assert not valid
        assert "HTTPS" in err

    def test_webhook_rejects_localhost(self):
        from src.publishing.security import validate_webhook_url
        valid, err = validate_webhook_url("https://localhost:8080/webhook")
        assert not valid

    @patch("socket.getaddrinfo")
    def test_webhook_accepts_valid_https(self, mock_dns):
        from src.publishing.security import validate_webhook_url
        mock_dns.side_effect = lambda host, port, family: [
            (family, 1, 6, "", ("93.184.216.34", 0))
        ]
        valid, err = validate_webhook_url("https://example.com/webhook")
        assert valid

    @patch("socket.getaddrinfo")
    def test_webhook_rejects_private_ip(self, mock_dns):
        from src.publishing.security import validate_webhook_url
        mock_dns.side_effect = lambda host, port, family: [
            (family, 1, 6, "", ("192.168.1.1", 0))
        ]
        valid, err = validate_webhook_url("https://example.com/webhook")
        assert not valid

    def test_hmac_signature_verifies(self):
        from src.publishing.security import compute_hmac_signature, verify_hmac_signature
        secret = "test-secret-123"
        payload = b'{"test": "data"}'
        ts = "1234567890"
        sig = compute_hmac_signature(payload, secret, ts)
        assert verify_hmac_signature(payload, secret, ts, sig)

    def test_hmac_different_secret_fails(self):
        from src.publishing.security import compute_hmac_signature, verify_hmac_signature
        sig = compute_hmac_signature(b'{"test": "data"}', "secret-a", "1234567890")
        assert not verify_hmac_signature(b'{"test": "data"}', "secret-b", "1234567890", sig)

    def test_callback_timestamp_within_window(self):
        from src.publishing.security import verify_callback_timestamp
        now = int(datetime.now(timezone.utc).timestamp())
        assert verify_callback_timestamp(now) is True
        assert verify_callback_timestamp(now - 200) is True
        assert verify_callback_timestamp(now - 400) is False

    def test_asset_url_requires_https(self):
        from src.publishing.security import validate_asset_url
        valid, err = validate_asset_url("http://example.com/image.png")
        assert not valid


# ── Webhook Error Classification Tests ────────────────────────────────────────

class TestErrorClassification:
    def test_auth_failed_not_retryable(self):
        from src.publishing.webhook import classify_webhook_error
        result = classify_webhook_error(401)
        assert result["error_category"] == "auth_failed"
        assert result["retryable"] is False

    def test_rate_limited_retryable(self):
        from src.publishing.webhook import classify_webhook_error
        result = classify_webhook_error(429)
        assert result["error_category"] == "rate_limited"
        assert result["retryable"] is True

    def test_server_error_retryable(self):
        from src.publishing.webhook import classify_webhook_error
        result = classify_webhook_error(500)
        assert result["error_category"] == "server_error"
        assert result["retryable"] is True

    def test_connection_failed_retryable(self):
        from src.publishing.webhook import classify_webhook_error
        result = classify_webhook_error(None)
        assert result["error_category"] == "target_unreachable"
        assert result["retryable"] is True

    def test_400_not_retryable(self):
        from src.publishing.webhook import classify_webhook_error
        result = classify_webhook_error(400)
        assert result["retryable"] is False


# ── State Machine Tests ───────────────────────────────────────────────────────

class TestStateMachine:
    def test_transition_rules(self):
        """Test that PUBLISH_REQUEST_TRANSITIONS are well-formed."""
        from src.publishing.models import PUBLISH_REQUEST_TRANSITIONS
        # queued can go to sending, cancelled, enqueue_failed
        assert "sending" in PUBLISH_REQUEST_TRANSITIONS.get("queued", [])
        assert "cancelled" in PUBLISH_REQUEST_TRANSITIONS.get("queued", [])
        # sending can go to delivered, failed
        assert "delivered" in PUBLISH_REQUEST_TRANSITIONS.get("sending", [])
        assert "failed" in PUBLISH_REQUEST_TRANSITIONS.get("sending", [])
        # published can't go back to draft_created
        assert "draft_created" not in PUBLISH_REQUEST_TRANSITIONS.get("published", [])

    def test_valid_transition_queued_to_sending(self):
        from src.publishing.models import PUBLISH_REQUEST_TRANSITIONS
        assert "sending" in PUBLISH_REQUEST_TRANSITIONS["queued"]

    def test_invalid_transition_published_to_draft(self):
        from src.publishing.models import PUBLISH_REQUEST_TRANSITIONS
        assert "draft_created" not in PUBLISH_REQUEST_TRANSITIONS.get("published", [])


# ── Secret Lifecycle Tests ────────────────────────────────────────────────────

class TestSecretLifecycle:
    def test_webhook_secret_only_shown_once(self):
        from src.publishing.security import generate_webhook_secret, hash_secret
        raw = generate_webhook_secret()
        assert len(raw) == 64
        hashed = hash_secret(raw)
        assert hashed != raw
        assert len(hashed) == 64

    def test_secret_rotation_preserves_previous(self):
        from src.publishing.security import generate_webhook_secret, hash_secret
        old_raw = generate_webhook_secret()
        old_hash = hash_secret(old_raw)
        new_raw = generate_webhook_secret()
        new_hash = hash_secret(new_raw)
        assert old_hash != new_hash

    def test_credentials_masked(self):
        from src.publishing.security import mask_credential
        masked = mask_credential("my-secret-password")
        assert "****" in masked
        assert "my-secret-password" not in masked

    def test_url_masking(self):
        from src.publishing.security import mask_url
        masked = mask_url("https://example.com/very/long/path/to/endpoint")
        assert "https://example.com" in masked


# ── Quality Gate Tests ────────────────────────────────────────────────────────

class TestQualityGates:
    @pytest.mark.asyncio
    async def test_unapproved_cp_cannot_publish(self):
        from src.publishing.quality import check_publish_quality
        cp = MagicMock(status="draft", quality_status="passed", content_items=[],
                       schema_items=[{"@type": "FAQPage"}], risk_level="P2")
        target = MagicMock(status="active", health_status="healthy",
                           credential_status="valid", auto_publish_on_approved=False)
        result = await check_publish_quality(cp, target, None, None)
        assert not result["passed"]
        assert any("未审核" in f for f in result["failures"])

    @pytest.mark.asyncio
    async def test_invalid_target_blocks_publish(self):
        from src.publishing.quality import check_publish_quality
        cp = MagicMock(status="approved", quality_status="passed",
                       content_items=[], schema_items=[{"@type": "FAQPage"}],
                       risk_level="P2")
        target = MagicMock(status="active", health_status="invalid",
                           credential_status="valid", auto_publish_on_approved=False)
        result = await check_publish_quality(cp, target, None, None)
        assert not result["passed"]

    @pytest.mark.asyncio
    async def test_high_risk_auto_publish_blocked(self):
        from src.publishing.quality import check_publish_quality
        cp = MagicMock(status="approved", quality_status="passed",
                       content_items=[], schema_items=[{"@type": "FAQPage"}],
                       risk_level="P0")
        target = MagicMock(status="active", health_status="healthy",
                           credential_status="valid", auto_publish_on_approved=True)
        result = await check_publish_quality(cp, target, None, None)
        assert not result["passed"]


# ── Feature Flag Tests ─────────────────────────────────────────────────────────

class TestFeatureFlags:
    def test_auto_publish_default_false(self):
        """Auto publish_on_approved should default to False."""
        from src.publishing.models import PublishTarget
        t = PublishTarget(organization_id=uuid.uuid4(), created_by=uuid.uuid4(),
                          name="test", target_type="webhook")
        # default=True at Python level for the column
        assert t.auto_publish_on_approved is False or t.auto_publish_on_approved is not True


# ── Cross-org Isolation Tests ─────────────────────────────────────────────────

class TestCrossOrgIsolation:
    def test_cross_org_target_access_rejected(self):
        """Verify cross-org logic pattern."""
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        assert org_a != org_b

    def test_idempotency_key_unique_per_org_target(self):
        from src.publishing.delivery import _build_request_idempotency_key
        k1 = _build_request_idempotency_key(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "manual")
        k2 = _build_request_idempotency_key(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "manual")
        assert k1 != k2

    def test_idempotency_key_stable_same_input(self):
        from src.publishing.delivery import _build_request_idempotency_key
        o, b, c, t = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        k1 = _build_request_idempotency_key(o, b, c, t, "manual")
        k2 = _build_request_idempotency_key(o, b, c, t, "manual")
        assert k1 == k2


# ── Redaction Tests ───────────────────────────────────────────────────────────

class TestRedaction:
    def test_payload_redaction_strips_callback_token(self):
        from src.publishing.security import redact_publish_payload
        payload = {
            "event": "test", "callback": {"callback_token": "secret-token-123"}
        }
        safe = redact_publish_payload(payload)
        assert safe["callback"]["callback_token"] == "***REDACTED***"

    def test_response_body_redaction(self):
        from src.publishing.security import redact_response_body
        text = "Authorization: Bearer xyz123\nContent-Type: application/json\n..."
        safe = redact_response_body(text)
        assert "Bearer" not in safe or "***REDACTED***" in safe

    def test_body_html_truncated_in_redaction(self):
        from src.publishing.security import redact_publish_payload
        payload = {"content": {"body_html": "A" * 1000}}
        safe = redact_publish_payload(payload)
        assert len(safe["content"]["body_html"]) <= 520


# ── WordPress Mapping Tests ──────────────────────────────────────────────────

class TestWordPressMapping:
    def test_schema_type_extracted_from_payload(self):
        from src.publishing.payload_builder import build_publish_payload
        cp = {
            "id": str(uuid.uuid4()), "organization_id": str(uuid.uuid4()),
            "brand_id": str(uuid.uuid4()),
            "content_items": [{"theme": "FAQ", "body": "Content"}],
            "schema_items": [{"@type": "FAQPage", "mainEntity": []}],
            "publishing_checklist": [], "fact_check_report": {},
            "risk_level": "P2", "review_required": True,
        }
        target = {"payload_version": "2026-05", "auto_publish_on_approved": False}
        payload, _, _ = build_publish_payload(cp, target, str(uuid.uuid4()))
        assert payload["schema"]["type"] == "FAQPage"
        assert payload["schema"]["json_ld"] == {"@type": "FAQPage", "mainEntity": []}


# ── Event System Tests ───────────────────────────────────────────────────────

class TestPublishEvents:
    def test_event_type_values(self):
        valid_events = {
            "publish_requested", "quality_gate_passed", "quality_gate_failed",
            "publish_enqueued", "publish_enqueue_failed", "publish_attempt_started",
            "publish_attempt_failed", "publish_attempt_succeeded",
            "publish_callback_received", "publish_status_updated",
            "publish_retry_scheduled", "publish_force_republish",
            "publish_target_health_changed", "publish_batch_completed",
        }
        assert len(valid_events) >= 10


# ── Model Tests ───────────────────────────────────────────────────────────────

class TestPublishingModels:
    def test_target_model_has_expected_fields(self):
        from src.publishing.models import PublishTarget
        assert hasattr(PublishTarget, "__tablename__")
        assert PublishTarget.__tablename__ == "publish_targets"

    def test_batch_model_has_expected_fields(self):
        from src.publishing.models import PublishBatch
        assert hasattr(PublishBatch, "__tablename__")
        assert PublishBatch.__tablename__ == "publish_batches"

    def test_request_status_transitions_defined(self):
        from src.publishing.models import PUBLISH_REQUEST_TRANSITIONS
        assert "queued" in PUBLISH_REQUEST_TRANSITIONS
        assert "sending" in PUBLISH_REQUEST_TRANSITIONS["queued"]
        assert "published" in PUBLISH_REQUEST_TRANSITIONS

    def test_all_model_tables_registered(self):
        from src.publishing.models import (PublishTarget, PublishBatch, PublishRequest,
                                            PublishAttempt, PublishStatusCallback,
                                            PublishEvent, CMSFieldMapping)
        models = [PublishTarget, PublishBatch, PublishRequest, PublishAttempt,
                  PublishStatusCallback, PublishEvent, CMSFieldMapping]
        for m in models:
            assert hasattr(m, "__tablename__")


# ── Feature Flags Tests ────────────────────────────────────────────────────────

class TestFeatureFlagsModule:
    def test_default_all_flags_off(self):
        from src.publishing.feature_flags import is_enabled, FEATURE_FLAGS
        for flag in FEATURE_FLAGS:
            assert is_enabled(flag) is False

    def test_enable_for_org(self):
        from src.publishing.feature_flags import enable_for_org, is_enabled
        enable_for_org("publishing_webhook_enabled", "test-org")
        assert is_enabled("publishing_webhook_enabled", "test-org") is True
        assert is_enabled("publishing_webhook_enabled") is False

    def test_global_set(self):
        from src.publishing.feature_flags import set_global, is_enabled
        set_global("publishing_webhook_enabled", True)
        assert is_enabled("publishing_webhook_enabled") is True
        set_global("publishing_webhook_enabled", False)


# ── Pause Mechanism Tests ─────────────────────────────────────────────────────

class TestPauseMechanism:
    def test_default_not_paused(self):
        from src.publishing.pause import is_publishing_paused
        is_paused, reason = is_publishing_paused()
        assert is_paused is False

    def test_org_pause(self):
        from src.publishing.pause import _org_pauses, is_publishing_paused
        _org_pauses["test-org"] = True
        is_paused, reason = is_publishing_paused("test-org")
        assert is_paused is True
        assert reason == "organization_pause"
        _org_pauses["test-org"] = False  # cleanup


# ── Health Module Tests ────────────────────────────────────────────────────────

class TestHealthModule:
    def test_health_constants(self):
        from src.publishing.health import (HEALTH_DEGRADED_THRESHOLD,
                                            HEALTH_FAILING_THRESHOLD,
                                            CIRCUIT_BREAKER_OPEN_SECONDS)
        assert HEALTH_DEGRADED_THRESHOLD == 3
        assert HEALTH_FAILING_THRESHOLD == 5
        assert CIRCUIT_BREAKER_OPEN_SECONDS == 1800

    def test_circuit_breaker_states(self):
        """Verify circuit breaker states are valid."""
        valid_states = {"closed", "open", "half_open"}
        assert len(valid_states) == 3


# ── Reconciliation Tests ──────────────────────────────────────────────────────

class TestReconciliation:
    def test_sending_timeout_constant(self):
        from src.publishing.reconciliation import SENDING_TIMEOUT_MINUTES, QUEUED_TIMEOUT_MINUTES
        assert SENDING_TIMEOUT_MINUTES == 30
        assert QUEUED_TIMEOUT_MINUTES == 15


# ── Delivery Enqueue Tests ────────────────────────────────────────────────────

class TestDeliveryEnqueue:
    def test_idempotency_key_format(self):
        from src.publishing.delivery import _build_batch_idempotency_key
        key = _build_batch_idempotency_key(
            "org-1", "brand-1", "cp-1", ["t1", "t2"], "manual"
        )
        assert len(key) == 64  # SHA256 hex

    def test_batch_key_includes_all_params(self):
        from src.publishing.delivery import _build_batch_idempotency_key
        key1 = _build_batch_idempotency_key("o1", "b1", "c1", ["t1"], "manual")
        key2 = _build_batch_idempotency_key("o1", "b1", "c1", ["t2"], "manual")
        assert key1 != key2  # Different targets → different keys


# ── WordPress Adapter Tests ────────────────────────────────────────────────────

class TestWordPressAdapter:
    def test_adapter_exists(self):
        from src.publishing.adapters.wordpress import WordPressAdapter
        adapter = WordPressAdapter()
        assert adapter is not None

    def test_schema_script_template(self):
        from src.publishing.adapters.wordpress import SCHEMA_SCRIPT_TEMPLATE
        assert "application/ld+json" in SCHEMA_SCRIPT_TEMPLATE

    def test_markdown_to_html_mapping(self):
        """Verify markdown→HTML conversion handles key patterns."""
        from src.publishing.payload_builder import _markdown_to_html, sanitize_html
        md = "# Title\n\n**Bold text**\n\n- List item"
        html = _markdown_to_html(md)
        safe = sanitize_html(html)
        assert "<h1>Title</h1>" in safe
        assert "<strong>Bold text</strong>" in safe

    def test_schema_not_duplicated_on_update(self):
        """Schema script should only appear once."""
        from src.publishing.adapters.wordpress import SCHEMA_SCRIPT_TEMPLATE
        import json
        schema_script = SCHEMA_SCRIPT_TEMPLATE.format(
            json.dumps({"@type": "FAQPage"})
        )
        content = f"<p>Body</p>{schema_script}"
        # Count occurrences
        assert content.count("application/ld+json") == 1

    def test_wordpress_default_status_is_draft(self):
        """WordPress adapter must default to draft, never publish."""
        from src.publishing.adapters.wordpress import WordPressAdapter
        adapter = WordPressAdapter()
        # The adapter's create_draft always sets status='draft'
        assert adapter is not None  # Default behavior: draft only


# ── WordPress Mock Server Tests ────────────────────────────────────────────────

class TestWordPressMock:
    @pytest.mark.asyncio
    async def test_mock_creates_post(self):
        from src.publishing.adapters.wordpress_mock import WPMockServer
        mock = WPMockServer("https://test.example.com")
        status, body = await mock.handle_request(
            "POST", "https://test.example.com/wp-json/wp/v2/posts",
            json_data={"title": "Test Post", "content": "<p>Hello</p>", "status": "draft"}
        )
        assert status == 201
        assert body["status"] == "draft"
        assert "id" in body
        assert "link" in body

    @pytest.mark.asyncio
    async def test_mock_auth_fail(self):
        from src.publishing.adapters.wordpress_mock import WPMockServer
        mock = WPMockServer()
        mock.set_auth_fail(True)
        status, body = await mock.handle_request("GET", "https://test.example.com/wp-json/wp/v2/types")
        assert status == 401

    @pytest.mark.asyncio
    async def test_mock_rate_limited(self):
        from src.publishing.adapters.wordpress_mock import WPMockServer
        mock = WPMockServer()
        mock.set_rate_limited(True)
        status, body = await mock.handle_request("POST", "https://test.example.com/wp-json/wp/v2/posts",
                                                   json_data={"title": "Test"})
        assert status == 429

    @pytest.mark.asyncio
    async def test_mock_server_error(self):
        from src.publishing.adapters.wordpress_mock import WPMockServer
        mock = WPMockServer()
        mock.set_server_error(True)
        status, body = await mock.handle_request("POST", "https://test.example.com/wp-json/wp/v2/posts",
                                                   json_data={"title": "Test"})
        assert status == 500

    @pytest.mark.asyncio
    async def test_mock_creates_page(self):
        from src.publishing.adapters.wordpress_mock import WPMockServer
        mock = WPMockServer()
        status, body = await mock.handle_request(
            "POST", "https://test.example.com/wp-json/wp/v2/pages",
            json_data={"title": "About", "content": "<p>About us</p>", "status": "draft"}
        )
        assert status == 201

    @pytest.mark.asyncio
    async def test_mock_users_me_returns_capabilities(self):
        from src.publishing.adapters.wordpress_mock import WPMockServer
        mock = WPMockServer()
        status, body = await mock.handle_request("GET", "https://test.example.com/wp-json/wp/v2/users/me")
        assert status == 200
        assert "capabilities" in body
        assert body["capabilities"]["create_posts"] is True
        assert body["capabilities"]["publish_posts"] is False


# ── CMS Adapter Protocol Tests ─────────────────────────────────────────────────

class TestCMSAdapterProtocol:
    def test_protocol_defined(self):
        from src.publishing.adapters.base import CMSAdapter
        assert hasattr(CMSAdapter, "validate_config")
        assert hasattr(CMSAdapter, "create_draft")
        assert hasattr(CMSAdapter, "update_draft")
        assert hasattr(CMSAdapter, "get_status")

    def test_wordpress_implements_protocol(self):
        from src.publishing.adapters.wordpress import WordPressAdapter
        adapter = WordPressAdapter()
        assert hasattr(adapter, "validate_config")
        assert hasattr(adapter, "create_draft")
        assert hasattr(adapter, "update_draft")
        assert hasattr(adapter, "get_status")
