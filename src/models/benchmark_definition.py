"""GEO Explorer — Benchmark Definition (P2-1). Freezes computation rules for auditability."""
from sqlalchemy import String, Float, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class BenchmarkDefinition(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "benchmark_definitions"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)

    sample_requirements: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {"min_brand_count_global": 10, "min_brand_count_org": 5, "min_run_count": 10,
    #  "min_success_rate": 0.70, "max_snapshot_age_days": 30, "min_platform_count": 2}

    aggregation_strategy: Mapped[str] = mapped_column(String(30), default="latest")
    # latest | period_average

    percentile_method: Mapped[str] = mapped_column(String(50), default="linear_interpolation")

    outlier_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {"method": "keep", "winsorize_pct": null}

    fallback_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {"order": ["primary", "category", "domain", "general"]}

    freshness_policy: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {"fresh_ttl_days": 3, "stale_ttl_days": 14, "expired_ttl_days": 30}

    kpi_normalization: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {"range": [0, 1]}

    material_gap_threshold: Mapped[float] = mapped_column(Float, default=0.05)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
