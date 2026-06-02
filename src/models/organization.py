from datetime import datetime
from sqlalchemy import String, Boolean, Integer, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin, UUIDMixin


class Organization(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="free")
    slug: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    brand_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    user_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    onboarding_step: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_brand_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_collection_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    users: Mapped[list["User"]] = relationship(back_populates="organization")
