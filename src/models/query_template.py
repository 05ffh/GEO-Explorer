import re
import uuid
from sqlalchemy import String, ForeignKey, Integer, Float, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from src.models.base import Base, TimestampMixin, UUIDMixin

QUESTION_TYPES = [
    "brand_definition",
    "brand_attribute",
    "brand_comparison",
    "brand_trust",
    "category_recommendation",
    "scenario_solution",
    "user_recommendation",
    "generic_advice",
]

_UNRESOLVED_RE = re.compile(r"\{[^{}]+\}")


class QueryTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "query_templates"

    VERSIONED_FIELDS = (
        "dimension", "template_text", "priority", "question_type",
        "brand_directed", "hallucination_check_enabled",
        "template_level", "question_scope",
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    template_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    question_type: Mapped[str] = mapped_column(String(50), default="brand_definition")
    brand_directed: Mapped[float] = mapped_column(Float, default=1.0)  # P1-4: 0/0.25/0.5/0.75/1.0
    hallucination_check_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    template_level: Mapped[str] = mapped_column(String(20), default="important")
    question_scope: Mapped[str | None] = mapped_column(String(30), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)

    @property
    def required_variables(self) -> list[str]:
        return [m.strip("{}") for m in _UNRESOLVED_RE.findall(self.template_text)]

    @property
    def answer_expected_subject(self) -> str:
        if self.question_type in ("brand_definition", "brand_attribute", "brand_trust"):
            return "brand"
        if self.question_type in ("brand_comparison",):
            return "brand_vs_competitor"
        if self.question_type in ("category_recommendation",):
            return "category_list"
        if self.question_type in ("scenario_solution",):
            return "scenario_list"
        if self.question_type in ("user_recommendation", "generic_advice"):
            return "generic"
        return "brand"
