"""GEO Explorer — Industry Classification Result model."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class IndustryClassificationResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "industry_classification_results"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)
    recommended_primary_template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("industry_templates.id"), nullable=True)
    recommended_secondary_template_ids: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    alternative_templates: Mapped[list] = mapped_column(JSONB, default=list)
    business_model_tags: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_json: Mapped[list] = mapped_column(JSONB, default=list)
    conflicts_json: Mapped[list] = mapped_column(JSONB, default=list)
    needs_user_confirmation: Mapped[bool] = mapped_column(Boolean, default=True)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
