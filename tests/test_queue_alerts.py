"""Tests for QueueAlert module (P1-5)."""
import uuid
import pytest
from src.queue.alerts import ALERT_TYPES, _build_dedupe_key


class TestAlertTypes:
    def test_all_alert_types_defined(self):
        expected = {
            "queue_backlog_high", "dlq_backlog_high", "worker_offline",
            "retry_spike", "task_failure_rate_high", "platform_circuit_open",
            "task_timeout_spike",
        }
        assert set(ALERT_TYPES.keys()) == expected

    def test_each_alert_has_severity_and_template(self):
        for alert_type, cfg in ALERT_TYPES.items():
            assert "severity" in cfg
            assert "message_tpl" in cfg

    def test_critical_alerts(self):
        critical_types = {"worker_offline", "task_failure_rate_high", "platform_circuit_open"}
        for atype in critical_types:
            assert ALERT_TYPES[atype]["severity"] == "critical"


class TestDedupeKey:
    def test_key_contains_all_parts(self):
        key = _build_dedupe_key("queue_backlog_high", "warning", "org-1", "geo_default", None)
        assert "queue_backlog_high" in key
        assert "warning" in key
        assert "org-1" in key
        assert "geo_default" in key

    def test_different_alert_types_different_keys(self):
        k1 = _build_dedupe_key("queue_backlog_high", "warning", None, None, None)
        k2 = _build_dedupe_key("dlq_backlog_high", "warning", None, None, None)
        assert k1 != k2

    def test_different_severity_different_keys(self):
        k1 = _build_dedupe_key("queue_backlog_high", "warning", None, None, None)
        k2 = _build_dedupe_key("queue_backlog_high", "critical", None, None, None)
        assert k1 != k2

    def test_different_org_different_keys(self):
        k1 = _build_dedupe_key("retry_spike", "warning", "org-1", None, None)
        k2 = _build_dedupe_key("retry_spike", "warning", "org-2", None, None)
        assert k1 != k2

    def test_different_platform_different_keys(self):
        k1 = _build_dedupe_key("platform_circuit_open", "critical", None, None, "kimi")
        k2 = _build_dedupe_key("platform_circuit_open", "critical", None, None, "deepseek")
        assert k1 != k2

    def test_same_params_same_key(self):
        k1 = _build_dedupe_key("dlq_backlog_high", "warning", "org-1", "geo_default", "kimi")
        k2 = _build_dedupe_key("dlq_backlog_high", "warning", "org-1", "geo_default", "kimi")
        assert k1 == k2
