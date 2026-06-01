import uuid
from decimal import Decimal
from sqlalchemy import String, ForeignKey, Integer, Numeric, Boolean, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class ApiUsage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_usage_logs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("collection_runs.id"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), server_default=text("''"), default="")
    model_name: Mapped[str] = mapped_column(String(100), server_default=text("''"), default="")
    query_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("query_results.id"), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(50), server_default=text("''"), default="")
    module_name: Mapped[str] = mapped_column(String(100), server_default=text("''"), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    input_cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    output_cost: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    currency: Mapped[str] = mapped_column(String(10), server_default=text("'CNY'"), default="CNY")
    pricing_version: Mapped[str] = mapped_column(String(50), server_default=text("''"), default="")
    estimated_cost: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str] = mapped_column(String(50), server_default=text("''"), default="")
    error_message: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    is_retry: Mapped[bool] = mapped_column(Boolean, default=False)
    billable: Mapped[bool] = mapped_column(Boolean, default=True)
    request_id: Mapped[str] = mapped_column(String(100), server_default=text("''"), default="")
    task_id: Mapped[str] = mapped_column(String(100), server_default=text("''"), default="")
    status: Mapped[str] = mapped_column(String(50), default="success")
