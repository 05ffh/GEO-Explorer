import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class CollectionRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "collection_runs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)    # 诊断单元·城市 "广州"
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 诊断单元·地区/商圈 "天河区"
    positioning_json: Mapped[dict] = mapped_column(JSONB, default=dict)     # 定位结果：tier/personas/competitors（主 agent 推断产出）
    sentiment_json: Mapped[dict] = mapped_column(JSONB, default=dict)       # 测量结果：负面率 store_level/brand_level（主 agent 调度产出）
    measurement_json: Mapped[dict] = mapped_column(JSONB, default=dict)     # 测量结果：命中率 judgments + 四切面（P3 产出，主 agent 判自然段式后回填）
    gt_facts_json: Mapped[dict] = mapped_column(JSONB, default=dict)        # 结构化 GT 事实清单（方案 C，主 agent 联网查证整理）
    cdp_facts_json: Mapped[dict] = mapped_column(JSONB, default=dict)       # CDP 多平台事实清单（中间处理层产出，主 agent 判断；核验后并入 gt_facts_json）
    trigger_type: Mapped[str] = mapped_column(String(50), default="manual")

    collection_status: Mapped[str] = mapped_column(String(50), default="pending")
    analysis_status: Mapped[str] = mapped_column(String(50), default="not_started")

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collection_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    total_queries: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

    execution_mode: Mapped[str] = mapped_column(String(20), default="celery")
    collection_error_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_error_trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    platform_status_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    progress_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    coverage_report_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analysis_skipped_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    template_version_ids: Mapped[dict] = mapped_column(JSONB, default=dict)
    preflight_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    report_quality_summary_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    template_health_report_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    report_publishable: Mapped[bool] = mapped_column(Boolean, default=False)
    blocking_reasons_json: Mapped[list] = mapped_column(JSONB, default=list)
