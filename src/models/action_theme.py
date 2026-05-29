import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

THEME_TRANSITIONS = {
    "detected": ["confirmed", "dismissed"],
    "confirmed": ["content_generating", "dismissed"],
    "content_generating": ["content_ready"],
    "content_ready": ["approved", "dismissed"],
    "approved": ["published_marked"],
    "published_marked": ["verification_pending"],
    "verification_pending": ["verified"],
    "verified": [],
    "dismissed": [],
}


class ActionTheme(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "action_themes"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="P1")
    issue_type: Mapped[str] = mapped_column(String(100), default="")
    affected_fields: Mapped[list] = mapped_column(JSONB, default=list)
    affected_platforms: Mapped[list] = mapped_column(JSONB, default=list)
    hallucination_result_ids: Mapped[list] = mapped_column(JSONB, default=list)
    action_plan_ids: Mapped[list] = mapped_column(JSONB, default=list)
    evidence_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    typical_ai_claims: Mapped[list] = mapped_column(JSONB, default=list)
    recommended_content_types: Mapped[list] = mapped_column(JSONB, default=list)
    expected_kpi_impact: Mapped[dict] = mapped_column(JSONB, default=dict)
    effort_level: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(30), default="detected")
