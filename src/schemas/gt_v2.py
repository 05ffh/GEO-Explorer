"""GT Schema v2 — Pydantic models, source tiers, compatibility layer, version detection."""
from typing import Literal
from pydantic import BaseModel, model_validator


# ── Source Tier definitions ──────────────────────────────────────────────

SOURCE_TIER_LABELS = {
    "S": "官方一手来源",
    "A": "权威第三方来源",
    "B": "可信媒体/专业机构",
    "C": "普通网页/百科/二手资料",
    "D": "未验证/低可信线索",
}

SOURCE_TIER_RANK = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}

SOURCE_TIER_USABLE_FOR_EVIDENCE = {"S", "A", "B"}  # min for P0/P1 hallucination

SOURCE_TYPE_OPTIONS = Literal[
    "official_site", "official_report", "regulatory",
    "industry_association", "media", "database", "manual", "other",
]


# ── Pydantic models ──────────────────────────────────────────────────────

class GtSource(BaseModel):
    tier: Literal["S", "A", "B", "C", "D"]
    source_type: SOURCE_TYPE_OPTIONS = "other"
    title: str = ""
    url: str = ""
    evidence_text: str = ""
    retrieved_at: str | None = None
    confirmed_by: str | None = None
    confirmed_at: str | None = None


class GtValue(BaseModel):
    value: str
    primary: bool = True
    sources: list[GtSource] = []


class GtField(BaseModel):
    field_type: Literal["string", "list", "number", "object"]
    values: list[GtValue] = []
    status: Literal["draft", "reviewed", "verified", "deprecated"] = "draft"

    @model_validator(mode="after")
    def _check_primary(self):
        primaries = [v for v in self.values if v.primary]
        if self.field_type != "list":
            if len(primaries) > 1:
                raise ValueError(
                    f"field_type={self.field_type} allows at most 1 primary, got {len(primaries)}"
                )
            if not primaries and self.values:
                self.values[0].primary = True  # auto-select first
        return self


class GtMeta(BaseModel):
    schema_version: Literal["gt_meta_v1"] = "gt_meta_v1"
    last_reviewed_by: str | None = None
    last_reviewed_at: str | None = None
    coverage_score: float = 0.0
    total_fields: int = 0
    completed_fields: int = 0
    required_fields: int = 0
    completed_required_fields: int = 0
    missing_required_fields: list[str] = []


class GroundTruthV2(BaseModel):
    schema_version: Literal["gt_v2"] = "gt_v2"
    fields: dict[str, GtField] = {}
    meta: GtMeta = GtMeta()


# ── Version detection ────────────────────────────────────────────────────

def detect_gt_schema_version(gt_json: dict | None, db_col: str | None = None) -> str:
    """Detect GT schema version: 'v1' or 'v2'."""
    if db_col == "gt_v2":
        return "v2"
    if isinstance(gt_json, dict) and gt_json.get("schema_version") == "gt_v2" and "fields" in gt_json:
        return "v2"
    return "v1"


# ── Compatibility layer ──────────────────────────────────────────────────

def gt_v2_to_flat(gt: GroundTruthV2 | dict) -> dict:
    """Convert v2 schema back to v1 flat format for existing consumers."""
    if isinstance(gt, dict):
        gt = GroundTruthV2.model_validate(gt)
    result: dict = {}
    for field_name, field in gt.fields.items():
        if not field.values:
            continue
        if field.field_type == "list":
            result[field_name] = [v.value for v in field.values if v.primary]
            if not result[field_name]:
                result[field_name] = [v.value for v in field.values]
        else:
            primary = next((v for v in field.values if v.primary), None)
            if primary:
                result[field_name] = primary.value
            elif field.values:
                result[field_name] = field.values[0].value
    return result


# ── Coverage score ───────────────────────────────────────────────────────

def compute_coverage_score(fields: dict, registry: dict | None = None) -> float:
    """Compute GT coverage score based on required fields from registry."""
    if registry is None:
        from src.schemas.gt_field_registry import GT_FIELD_REGISTRY as registry  # noqa: F811
    required = {k for k, d in registry.items() if d.required}
    if not required:
        return 0.0
    completed = sum(
        1 for k in required
        if k in fields and hasattr(fields[k], 'values') and fields[k].values
    )
    return round(completed / len(required), 4)


# ── Field sources helpers ────────────────────────────────────────────────

def get_field_sources_from_json(gt_json: dict, field_name: str,
                                 source_urls: list | None = None) -> list[dict]:
    """Extract sources for a field from GT JSON (v1 or v2)."""
    v = detect_gt_schema_version(gt_json)
    if v == "v1":
        return [{"tier": "C", "url": u, "source_type": "other"}
                for u in (source_urls or [])]
    field = gt_json.get("fields", {}).get(field_name, {})
    sources = []
    for val in (field.get("values") or []):
        for src in (val.get("sources") or []):
            sources.append(src)
    return sources


def get_best_source_for_field(gt_json: dict, field_name: str,
                                source_urls: list | None = None,
                                min_tier: str = "B") -> dict | None:
    """Return highest-tier source >= min_tier. Used for hallucination evidence."""
    min_rank = SOURCE_TIER_RANK.get(min_tier, 3)
    best = None
    best_rank = 0
    for src in get_field_sources_from_json(gt_json, field_name, source_urls):
        r = SOURCE_TIER_RANK.get(src.get("tier", "C"), 2)
        if r >= min_rank and r > best_rank:
            best = src
            best_rank = r
    return best
