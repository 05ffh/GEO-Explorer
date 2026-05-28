import uuid
from sqlalchemy import String, ForeignKey, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class QueryTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "query_templates"
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
