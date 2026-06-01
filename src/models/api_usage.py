"""GEO Explorer — API Usage Log (extended for cost governance)."""
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, ForeignKey, Integer, Numeric, Boolean, Text, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class ApiUsage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "api_usage_logs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
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
    status: Mapped[str] = mapped_column(String(50), default="success")
    error_code: Mapped[str] = mapped_column(String(100), server_default=text("''"), default="")
    error_message: Mapped[str] = mapped_column(Text, server_default=text("''"), default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    is_retry: Mapped[bool] = mapped_column(Boolean, default=False)
    billable: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str] = mapped_column(String(100), server_default=text("''"), default="")
    task_id: Mapped[str] = mapped_column(String(100), server_default=text("''"), default="")
    gt_candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("gt_candidates.id"), nullable=True)
    action_theme_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("action_themes.id"), nullable=True)
    content_package_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("content_packages.id"), nullable=True)


class ModelPricing(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "model_pricing"
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_price_per_1k_tokens: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    output_price_per_1k_tokens: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    cached_price_per_1k_tokens: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    request_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    pricing_version: Mapped[str] = mapped_column(String(20), default="1.0")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class UsageBudget(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "usage_budgets"
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    period: Mapped[str] = mapped_column(String(20), default="monthly")
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    alert_thresholds: Mapped[list] = mapped_column(JSONB, default=[80, 90, 100])
    hard_limit_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class CostAlert(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cost_alerts"
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
