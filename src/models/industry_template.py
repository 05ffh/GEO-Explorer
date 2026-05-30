"""GEO Explorer — Industry Template & Query Template models."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, ForeignKey, DateTime, Text, Float, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class IndustryTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "industry_templates"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("industry_templates.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(50), default="domain")
    domain: Mapped[str] = mapped_column(String(100), default="")
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[str] = mapped_column(String(20), default="1.0")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    region: Mapped[str] = mapped_column(String(50), default="CN")
    locale: Mapped[str] = mapped_column(String(10), default="zh-CN")
    business_model_tags: Mapped[list] = mapped_column(JSONB, default=list)
    # GT
    required_gt_fields: Mapped[list] = mapped_column(JSONB, default=list)
    optional_gt_fields: Mapped[list] = mapped_column(JSONB, default=list)
    high_risk_gt_fields: Mapped[list] = mapped_column(JSONB, default=list)
    industry_specific_fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    field_evidence_requirements: Mapped[dict] = mapped_column(JSONB, default=dict)
    gt_field_weights: Mapped[dict] = mapped_column(JSONB, default=dict)
    # KPI
    kpi_weights: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 竞品
    competitor_rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 风险
    risk_rules: Mapped[list] = mapped_column(JSONB, default=list)
    compliance_constraints: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Action & Content
    action_rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    content_templates: Mapped[dict] = mapped_column(JSONB, default=dict)
    review_rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 审计
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    change_log: Mapped[list] = mapped_column(JSONB, default=list)


class IndustryQueryTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "industry_query_templates"
    industry_template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("industry_templates.id"), nullable=False, index=True)
    dimension: Mapped[str] = mapped_column(String(100), default="")
    intent: Mapped[str] = mapped_column(String(100), default="")
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    uses_brand_name: Mapped[bool] = mapped_column(Boolean, default=True)
    target_kpis: Mapped[list] = mapped_column(JSONB, default=list)
    target_gt_fields: Mapped[list] = mapped_column(JSONB, default=list)
    risk_level: Mapped[str] = mapped_column(String(10), default="P1")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
