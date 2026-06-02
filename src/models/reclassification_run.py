"""ReclassificationRun — batch management for historical report re-attribution (P1-8)."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text as sa_text
from src.models.base import Base

STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_PARTIAL_FAILED = "partial_failed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
RECLASSIFICATION_STATUSES = [STATUS_QUEUED, STATUS_RUNNING, STATUS_COMPLETED, STATUS_PARTIAL_FAILED, STATUS_FAILED, STATUS_CANCELLED]

MODE_DRY_RUN = "dry_run"
MODE_WRITE_RESULTS = "write_new_results"
MODE_PUBLISH_SUMMARY = "publish_corrected_summary"
MODE_GENERATE_REPORT = "generate_corrected_report"
RECLASSIFICATION_MODES = [MODE_DRY_RUN, MODE_WRITE_RESULTS, MODE_PUBLISH_SUMMARY, MODE_GENERATE_REPORT]

RESULT_ORIGINAL = "original"
RESULT_RECLASSIFIED = "reclassified"


class ReclassificationRun(Base):
    __tablename__ = "reclassification_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)

    from_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    to_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(32), default=STATUS_QUEUED)
    mode: Mapped[str] = mapped_column(String(32), default=MODE_DRY_RUN)
    trigger_source: Mapped[str] = mapped_column(String(32), default="manual")

    detector_version: Mapped[str] = mapped_column(String(64), default="p0-7-v1")
    quality_schema_version: Mapped[str] = mapped_column(String(64), default="template_health_v1")
    metric_mapping_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gt_schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gt_version_strategy: Mapped[str] = mapped_column(String(32), default="latest_active")
    detector_config_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    eligible_runs_count: Mapped[int] = mapped_column(Integer, default=0)
    runs_processed: Mapped[int] = mapped_column(Integer, default=0)
    runs_failed: Mapped[int] = mapped_column(Integer, default=0)
    query_results_processed: Mapped[int] = mapped_column(Integer, default=0)
    hallucination_results_created: Mapped[int] = mapped_column(Integer, default=0)

    classification_changes_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    progress_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    sample_diffs_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    run_original_summaries_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    official: Mapped[bool] = mapped_column(Boolean, default=False)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reclassification_runs.id"), nullable=True)
    is_current_for_range: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    triggered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa_text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa_text("now()"))
