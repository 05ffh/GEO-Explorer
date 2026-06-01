"""Tests for idempotency module (P1-5)."""
import pytest
from src.queue.idempotency import (
    build_idempotency_key, build_payload_hash, build_time_bucket,
)


class TestBuildIdempotencyKey:
    def test_key_contains_org_id(self):
        key = build_idempotency_key(
            org_id="org-123", task_name="collect_brand_task",
            operation_type="full_collect", payload_hash="abc123", time_bucket="2026053015",
        )
        assert "org-123" in key

    def test_key_contains_operation_type(self):
        key = build_idempotency_key(
            org_id="org-1", task_name="src.collector.tasks.collect_brand_task",
            operation_type="gt_collection", payload_hash="def", time_bucket="2026053015",
        )
        assert "gt_collection" in key

    def test_key_uses_short_task_name(self):
        key = build_idempotency_key(
            org_id="org-1", task_name="src.collector.tasks.collect_brand_task",
            operation_type="full", payload_hash="x", time_bucket="2026053015",
        )
        assert "collect_brand_task" in key
        assert "src.collector.tasks" not in key

    def test_key_differs_by_org_id(self):
        k1 = build_idempotency_key(org_id="org-1", task_name="t", operation_type="o", payload_hash="h", time_bucket="b")
        k2 = build_idempotency_key(org_id="org-2", task_name="t", operation_type="o", payload_hash="h", time_bucket="b")
        assert k1 != k2

    def test_key_differs_by_operation_type(self):
        k1 = build_idempotency_key(org_id="o", task_name="t", operation_type="full", payload_hash="h", time_bucket="b")
        k2 = build_idempotency_key(org_id="o", task_name="t", operation_type="gt", payload_hash="h", time_bucket="b")
        assert k1 != k2

    def test_key_differs_by_payload_hash(self):
        k1 = build_idempotency_key(org_id="o", task_name="t", operation_type="o", payload_hash="a", time_bucket="b")
        k2 = build_idempotency_key(org_id="o", task_name="t", operation_type="o", payload_hash="b", time_bucket="b")
        assert k1 != k2

    def test_key_differs_by_time_bucket(self):
        k1 = build_idempotency_key(org_id="o", task_name="t", operation_type="o", payload_hash="h", time_bucket="2026053014")
        k2 = build_idempotency_key(org_id="o", task_name="t", operation_type="o", payload_hash="h", time_bucket="2026053015")
        assert k1 != k2


class TestPayloadHash:
    def test_same_args_produce_same_hash(self):
        h1 = build_payload_hash(["a", "b"], {"c": "d"})
        h2 = build_payload_hash(["a", "b"], {"c": "d"})
        assert h1 == h2

    def test_different_args_produce_different_hash(self):
        h1 = build_payload_hash(["a"], {})
        h2 = build_payload_hash(["b"], {})
        assert h1 != h2

    def test_hash_is_16_chars(self):
        h = build_payload_hash(["a"], {"b": "c"})
        assert len(h) == 16

    def test_kwargs_order_independent(self):
        h1 = build_payload_hash([], {"a": "1", "b": "2"})
        h2 = build_payload_hash([], {"b": "2", "a": "1"})
        assert h1 == h2


class TestTimeBucket:
    def test_time_bucket_format(self):
        tb = build_time_bucket()
        assert len(tb) == 10  # YYYYMMDDHH
        assert tb.isdigit()
