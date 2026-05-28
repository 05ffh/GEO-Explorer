import uuid
from decimal import Decimal
from sqlalchemy import String, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class ApiUsage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_usage_logs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_runs.id"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    query_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_results.id"), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    status: Mapped[str] = mapped_column(String(50), default="success")
