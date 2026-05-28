import uuid
from sqlalchemy import String, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

VALID_TRANSITIONS = {
    "pending": ["in_progress", "cancelled"],
    "in_progress": ["completed", "cancelled"],
    "completed": ["verified", "reopened"],
    "verified": [],
    "cancelled": [],
    "reopened": ["in_progress"],
}


class ActionPlan(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "action_plans"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), default="")
    priority: Mapped[str] = mapped_column(String(10), default="P2")
    evidence_hallucination_ids: Mapped[list] = mapped_column(JSONB, default=list)
    ai_wrong_claims: Mapped[dict] = mapped_column(JSONB, default=dict)
    correct_ground_truth: Mapped[dict] = mapped_column(JSONB, default=dict)
    suggested_content_type: Mapped[str] = mapped_column(String(100), default="")
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    target_page: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
