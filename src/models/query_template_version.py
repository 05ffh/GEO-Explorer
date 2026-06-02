"""QueryTemplateVersion — shadow table for template version history."""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Float, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text as sa_text
from src.models.base import Base


class QueryTemplateVersion(Base):
    __tablename__ = "query_template_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_templates.id", ondelete="RESTRICT"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)

    # versioned fields snapshot
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    question_type: Mapped[str] = mapped_column(String(50), default="brand_definition")
    brand_directed: Mapped[float] = mapped_column(Float, default=1.0)
    hallucination_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    template_level: Mapped[str] = mapped_column(String(20), default="important")
    question_scope: Mapped[str | None] = mapped_column(String(30), nullable=True)
    required_variables: Mapped[list] = mapped_column(JSONB, default=list)
    applicable_industries: Mapped[list] = mapped_column(JSONB, default=list)
    excluded_industries: Mapped[list] = mapped_column(JSONB, default=list)
    metric_eligibility: Mapped[dict] = mapped_column(JSONB, default=dict)

    # version metadata
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=sa_text("now()"), nullable=False)

    __table_args__ = ()
