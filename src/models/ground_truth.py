import uuid
from sqlalchemy import String, ForeignKey, Integer, Float, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin


class GroundTruthVersion(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ground_truth_versions"
    brand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("brands.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    ground_truth_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_urls: Mapped[list] = mapped_column(ARRAY(Text), default=list)
    reviewer: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default="draft")
    required_fields_complete: Mapped[bool] = mapped_column(default=False)
    user_confirmed: Mapped[bool] = mapped_column(default=False)
    high_risk_fields_reviewed: Mapped[bool] = mapped_column(default=False)
    gt_coverage_rate: Mapped[float] = mapped_column(Float, default=0.0)
    gt_schema_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def get_flat_json(self) -> dict:
        """Return flat dict for consumers, auto-detecting v1/v2."""
        from src.schemas.gt_v2 import detect_gt_schema_version, gt_v2_to_flat
        v = detect_gt_schema_version(self.ground_truth_json, self.gt_schema_version)
        if v == "v1":
            return self.ground_truth_json
        return gt_v2_to_flat(self.ground_truth_json)

    def get_field_sources(self, field_name: str) -> list[dict]:
        """Return sources for a specific field (v1: global sources, v2: field-level)."""
        from src.schemas.gt_v2 import detect_gt_schema_version
        v = detect_gt_schema_version(self.ground_truth_json, self.gt_schema_version)
        if v == "v1":
            return [{"tier": "C", "url": u, "source_type": "other"}
                    for u in (self.source_urls or [])]
        field = self.ground_truth_json.get("fields", {}).get(field_name, {})
        sources = []
        for val in (field.get("values") or []):
            for src in (val.get("sources") or []):
                sources.append(src)
        return sources

    def get_best_source_for_field(self, field_name: str, min_tier: str = "B") -> dict | None:
        """Return highest-tier source >= min_tier for hallucination evidence."""
        from src.schemas.gt_v2 import SOURCE_TIER_RANK
        min_rank = SOURCE_TIER_RANK.get(min_tier, 3)
        best = None
        best_rank = 0
        for src in self.get_field_sources(field_name):
            r = SOURCE_TIER_RANK.get(src.get("tier", "C"), 2)
            if r >= min_rank and r > best_rank:
                best = src
                best_rank = r
        return best
