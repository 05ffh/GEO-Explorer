"""GEO Explorer — Report Artifact (P1-6 customer report language)."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class ReportArtifact(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "report_artifacts"

    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_runs.id"), nullable=False)
    edition: Mapped[str] = mapped_column(String(30), nullable=False)  # executive/implementation/customer
    format: Mapped[str] = mapped_column(String(10), nullable=False)    # md/pdf/docx
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)  # SHA256
    report_version: Mapped[int] = mapped_column(Integer, default=1)
    template_version: Mapped[str] = mapped_column(String(20), default="1.0")
    language_version: Mapped[str] = mapped_column(String(20), default="1.0")
    industry_template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("industry_templates.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="not_generated", index=True)
    # not_generated / queued / generating / generated / quality_failed / failed / stale / deleted
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # passed/warning/failed
    quality_report_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    last_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    superseded_by_report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_artifacts.id"), nullable=True)
    generation_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="zh-CN")
