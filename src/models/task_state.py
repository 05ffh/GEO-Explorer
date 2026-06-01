"""GEO Explorer — Task State, Task Event (P1-5 queue stability)."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Float, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

# Task status enum — valid states and transitions
TASK_STATUS_TRANSITIONS = {
    "queued":          {"running", "cancelled", "blocked", "expired"},
    "scheduled":       {"queued", "cancelled"},
    "running":         {"completed", "failed", "retrying", "cancelled"},
    "retrying":        {"running", "failed", "cancelled"},
    "completed":       set(),
    "failed":          {"dead_lettered"},
    "cancelled":       set(),
    "dead_lettered":   {"requeued"},
    "requeued":        {"queued"},
    "blocked":         {"queued", "cancelled"},
    "expired":         set(),
    "duplicate":       set(),
    "enqueue_failed":  {"queued"},
}

TERMINAL_STATUSES = {"completed", "cancelled", "expired", "duplicate"}


class TaskState(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "task_states"

    celery_task_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    root_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    parent_task_state_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    queue_name: Mapped[str] = mapped_column(String(100), default="geo_default")
    routing_key: Mapped[str] = mapped_column(String(100), default="default")
    priority: Mapped[int] = mapped_column(Integer, default=5)

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)

    operation_type: Mapped[str] = mapped_column(String(50), default="")
    trigger_type: Mapped[str] = mapped_column(String(50), default="manual")
    args_json: Mapped[list] = mapped_column(JSONB, default=[])
    kwargs_json: Mapped[dict] = mapped_column(JSONB, default={})
    payload_hash: Mapped[str] = mapped_column(String(64), default="")

    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    idempotency_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_ttl: Mapped[int] = mapped_column(Integer, default=3600)

    execution_lock_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    execution_lock_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    progress: Mapped[float] = mapped_column(Float, default=0.0)
    progress_message: Mapped[str] = mapped_column(String(500), default="")
    last_progress_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)

    dlq_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dlq_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dlq_retry_policy: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dlq_requeue_count: Mapped[int] = mapped_column(Integer, default=0)
    dlq_max_requeues: Mapped[int] = mapped_column(Integer, default=3)
    dlq_backoff_seconds: Mapped[int] = mapped_column(Integer, default=300)
    next_requeue_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    control_action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_states.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSONB, default={})
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
