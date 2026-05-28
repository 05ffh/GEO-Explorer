import uuid
from sqlalchemy import String, ForeignKey, Integer, Text
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
