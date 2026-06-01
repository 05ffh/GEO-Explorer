import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

CONTENT_PACKAGE_TRANSITIONS = {
    "draft": ["fact_checked", "cancelled"],
    "fact_checked": ["needs_review", "approved"],
    "needs_review": ["approved", "draft"],
    "approved": ["exported"],
    "exported": ["published"],
    "published": ["verification_pending"],
    "verification_pending": ["verified"],
    "verified": [],
    "cancelled": [],
}


class ContentPackage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "content_packages"
    action_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("action_plans.id"), nullable=True)
    action_theme_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("action_themes.id"), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    content_items: Mapped[list] = mapped_column(JSONB, default=list)
    schema_items: Mapped[list] = mapped_column(JSONB, default=list)
    publishing_checklist: Mapped[list] = mapped_column(JSONB, default=list)
    fact_check_report: Mapped[dict] = mapped_column(JSONB, default=dict)
    fact_source_map: Mapped[dict] = mapped_column(JSONB, default=dict)
    risk_level: Mapped[str] = mapped_column(String(10), default="low")
    publish_url: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_platform: Mapped[str] = mapped_column(String(50), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publish_status_summary: Mapped[str] = mapped_column(String(30), default="not_published")
    published_target_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_target_count: Mapped[int] = mapped_column(Integer, default=0)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
