import uuid
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class ContentPackage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "content_packages"
    action_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("action_plans.id"), nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    content_items: Mapped[dict] = mapped_column(JSONB, default=list)
    schema_items: Mapped[dict] = mapped_column(JSONB, default=list)
    publishing_checklist: Mapped[dict] = mapped_column(JSONB, default=list)
    fact_check_report: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")
