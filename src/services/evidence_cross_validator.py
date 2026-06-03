"""P2-2: Evidence Cross Validator — multi-source GT evidence consensus engine.

Uses GT v2 multi-source structure (GtValue.sources[]) to compute evidence
strength, consensus, and conflict levels for claim verification.

Architecture:
- base_verdict (supported/contradicted/...) — fact check result (existing)
- evidence_strength_level (strong/moderate/weak/disputed/...) — evidence quality
- evidence_consensus_json — full snapshot persisted on HallucinationResult
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from src.schemas.gt_v2 import (
    SOURCE_TIER_RANK, SOURCE_TIER_USABLE_FOR_EVIDENCE,
    detect_gt_schema_version,
)


# ── Enums ───────────────────────────────────────────────────────────────────

class EvidenceStrengthLevel(str, Enum):
    STRONG = "strong"           # agreement >= 0.7, best_tier S/A, >= 2 sources
    MODERATE = "moderate"       # agreement >= 0.5, best_tier A/B
    WEAK = "weak"               # best_tier C or agreement < 0.5
    DISPUTED = "disputed"       # conflicting sources
    INSUFFICIENT = "insufficient_evidence"  # no sources
    UNAVAILABLE = "unavailable"  # v1 GT (no source structure)


class ConflictLevel(str, Enum):
    NONE = "none"
    WEAK = "weak_conflict"          # non-consensus values only C/D support
    MODERATE = "moderate_conflict"  # non-consensus values have B support
    STRONG = "strong_conflict"      # non-consensus values have A/S support
    CRITICAL = "critical_conflict"  # S/A sources disagree on critical field


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class ValueVariant:
    """One normalized value with its supporting sources."""
    normalized_value: str
    raw_values: list[str] = field(default_factory=list)
    source_count: int = 0
    weighted_score: float = 0.0
    best_tier: str = "D"
    best_source: dict | None = None
    tiers: dict[str, int] = field(default_factory=dict)  # {"S": 1, "A": 2, ...}


@dataclass
class FieldEvidence:
    """Complete evidence snapshot for one GT field."""
    field_name: str
    schema_version: str = "evidence_v1"
    gt_schema: str = "v1"  # v1 or v2
    total_sources: int = 0
    distinct_raw_values: int = 0
    variants: list[ValueVariant] = field(default_factory=list)
    consensus_value: str = ""
    consensus_variant: ValueVariant | None = None
    agreement_ratio: float = 0.0
    weighted_agreement_ratio: float = 0.0
    best_tier: str = "D"
    best_source: dict | None = None
    has_conflict: bool = False
    conflict_level: ConflictLevel = ConflictLevel.NONE
    is_critical_field: bool = False
    excluded_sources: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class EvidenceConsensusResult:
    """Per-claim cross-validation result."""
    field_name: str
    base_verdict: str  # supported/contradicted/unsupported — existing fact verdict
    evidence_strength_level: EvidenceStrengthLevel
    agreement_ratio: float
    total_sources: int
    supporting_sources: int
    best_tier: str
    best_source: dict | None
    consensus_value: str
    has_conflict: bool
    conflict_level: ConflictLevel
    value_variants: list[dict] = field(default_factory=list)
    excluded_sources: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "schema_version": "evidence_consensus_v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "field_name": self.field_name,
            "base_verdict": self.base_verdict,
            "evidence_strength_level": self.evidence_strength_level.value,
            "agreement_ratio": self.agreement_ratio,
            "total_sources": self.total_sources,
            "supporting_sources": self.supporting_sources,
            "best_tier": self.best_tier,
            "best_source": self.best_source,
            "consensus_value": self.consensus_value,
            "has_conflict": self.has_conflict,
            "conflict_level": self.conflict_level.value,
            "value_variants": self.value_variants,
            "excluded_sources": self.excluded_sources,
            "notes": self.notes,
        }


# ── Critical fields (high-risk for conflict escalation) ─────────────────────

CRITICAL_FIELDS = {
    "official_name", "industry", "category", "core_products",
    "regulatory_status", "financial_performance", "health_effect",
    "legal_compliance", "pricing", "positioning",
}


# ── Value normalization ────────────────────────────────────────────────────

# Common aliases for Chinese/English value normalization
_VALUE_ALIASES = {
    "星冰乐": ["frappuccino", "星巴克星冰乐"],
    "frappuccino": ["星冰乐", "星巴克星冰乐"],
    "saas": ["software-as-a-service", "software as a service"],
    "software-as-a-service": ["saas", "software as a service"],
}


def _normalize_value(value: str, field_name: str = "") -> str:
    """Normalize a GT value for consensus comparison.

    Rules: lowercase, trim, full-width→half-width, common alias mapping.
    """
    if not value:
        return ""
    v = value.strip().lower()
    # Full-width to half-width
    v = v.translate(str.maketrans(
        "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
        "０１２３４５６７８９",
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789",
    ))
    # Normalize whitespace
    v = re.sub(r'\s+', ' ', v)
    # Remove common brand name prefix only if followed by more content
    v = re.sub(r'^(星巴克|starbucks)\s+(.+)', r'\2', v)
    # Normalize punctuation
    v = v.replace('，', ',').replace('。', '.').replace('、', ',')
    v = v.replace('（', '(').replace('）', ')').replace('：', ':')
    return v.strip()


def _values_match(norm_a: str, norm_b: str) -> bool:
    """Check if two normalized values match (including alias lookup)."""
    if norm_a == norm_b:
        return True
    aliases_a = _VALUE_ALIASES.get(norm_a, [])
    aliases_b = _VALUE_ALIASES.get(norm_b, [])
    if norm_a in aliases_b or norm_b in aliases_a:
        return True
    return bool(set(aliases_a) & set(aliases_b))


# ── Source weight calculation ────────────────────────────────────────────────

def compute_source_weight(src: dict) -> float:
    """Compute weighted score for a source.

    Base: S=5, A=4, B=3, C=2, D=1
    Multipliers: official_source ×1.2, evidence_text ×1.1, confirmed ×1.1
    D-tier capped at 1.0 regardless of multipliers.
    """
    tier = src.get("tier", "C")
    base = float(SOURCE_TIER_RANK.get(tier, 2))

    multiplier = 1.0
    source_type = src.get("source_type", "other")
    if source_type in ("official_site", "official_report", "regulatory"):
        multiplier *= 1.2
    if src.get("evidence_text", "").strip():
        multiplier *= 1.1
    if src.get("confirmed_by"):
        multiplier *= 1.1

    weight = base * multiplier

    # D-tier never exceeds 1.0
    if tier == "D":
        weight = min(weight, 1.0)

    return round(weight, 3)


# ── Cache ───────────────────────────────────────────────────────────────────

class EvidenceCache:
    """Run-level cache: (gt_version_id, field_name) → FieldEvidence."""

    def __init__(self):
        self._cache: dict[tuple, FieldEvidence] = {}

    def get(self, gt_version_id: str, field_name: str) -> FieldEvidence | None:
        return self._cache.get((str(gt_version_id), field_name))

    def set(self, gt_version_id: str, field_name: str, evidence: FieldEvidence):
        self._cache[(str(gt_version_id), field_name)] = evidence

    def clear(self):
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


# ── Main validator ─────────────────────────────────────────────────────────

class EvidenceCrossValidator:
    """Multi-source GT evidence cross-validator with field-level caching."""

    def __init__(self, gt_version):
        self.gt_version = gt_version
        self.gt_version_id = str(gt_version.id) if hasattr(gt_version, "id") else "unknown"
        self.gt_json = gt_version.ground_truth_json if hasattr(gt_version, "ground_truth_json") else {}
        self.source_urls = getattr(gt_version, "source_urls", []) or []
        self.gt_schema = detect_gt_schema_version(self.gt_json, getattr(gt_version, "gt_schema_version", None))
        self.cache = EvidenceCache()

    def build_field_evidence(self, field_name: str) -> FieldEvidence:
        """Build complete FieldEvidence for a GT field (cached)."""
        cached = self.cache.get(self.gt_version_id, field_name)
        if cached:
            return cached

        evidence = self._build_uncached(field_name)
        self.cache.set(self.gt_version_id, field_name, evidence)
        return evidence

    def _build_uncached(self, field_name: str) -> FieldEvidence:
        """Build FieldEvidence from GT — handles v1/v2/no-sources degradation."""
        evidence = FieldEvidence(
            field_name=field_name,
            gt_schema=self.gt_schema,
            is_critical_field=field_name in CRITICAL_FIELDS,
        )

        # v1 GT: no source structure
        if self.gt_schema == "v1":
            evidence.notes.append("v1 GT — 无多来源结构，证据不可用")
            if self.source_urls:
                evidence.total_sources = len(self.source_urls)
                evidence.best_tier = "C"
                evidence.notes.append(f"v1 全局来源 {evidence.total_sources} 个，统一为 C 级")
            return evidence

        # v2 GT: extract field data
        field_data = self.gt_json.get("fields", {}).get(field_name, {})
        values = field_data.get("values", [])

        if not values:
            evidence.notes.append("字段无 GtValue 条目")
            return evidence

        # Build value variants with normalization
        variant_map: dict[str, ValueVariant] = {}
        all_sources = []

        for val_entry in values:
            raw_value = str(val_entry.get("value", ""))
            norm = _normalize_value(raw_value, field_name)
            sources = val_entry.get("sources", [])

            # Find or create matching variant
            matched_key = None
            for key in variant_map:
                if _values_match(norm, key):
                    matched_key = key
                    break

            if matched_key:
                variant = variant_map[matched_key]
                if raw_value not in variant.raw_values:
                    variant.raw_values.append(raw_value)
            else:
                variant = ValueVariant(
                    normalized_value=norm,
                    raw_values=[raw_value] if raw_value else [],
                )
                variant_map[norm] = variant

            # Process sources for this value entry
            for src in sources:
                all_sources.append(src)
                weight = compute_source_weight(src)
                variant.source_count += 1
                variant.weighted_score += weight
                tier = src.get("tier", "D")
                variant.tiers[tier] = variant.tiers.get(tier, 0) + 1

                # Track best source per variant
                tier_rank = SOURCE_TIER_RANK.get(tier, 1)
                if variant.best_source is None or tier_rank > SOURCE_TIER_RANK.get(
                    variant.best_source.get("tier", "D"), 1
                ):
                    variant.best_source = src
                    variant.best_tier = tier

        evidence.total_sources = len(all_sources)
        evidence.variants = list(variant_map.values())
        evidence.distinct_raw_values = len(
            set(rv for v in evidence.variants for rv in v.raw_values)
        )

        if not evidence.variants:
            evidence.notes.append("字段无有效来源")
            return evidence

        # Sort variants by weighted_score descending
        evidence.variants.sort(key=lambda v: v.weighted_score, reverse=True)

        # Consensus = highest weighted_score variant
        consensus_variant = evidence.variants[0]
        evidence.consensus_value = consensus_variant.normalized_value
        evidence.consensus_variant = consensus_variant
        evidence.best_tier = consensus_variant.best_tier
        evidence.best_source = consensus_variant.best_source

        # Compute agreement ratios
        total_weight = sum(v.weighted_score for v in evidence.variants)
        if total_weight > 0:
            evidence.weighted_agreement_ratio = round(consensus_variant.weighted_score / total_weight, 4)
        supporting = consensus_variant.source_count
        evidence.agreement_ratio = round(supporting / evidence.total_sources, 4) if evidence.total_sources else 0.0

        # Assess conflict
        if len(evidence.variants) > 1:
            evidence.has_conflict = True
            evidence.conflict_level = self._assess_conflict_level(evidence)
        else:
            evidence.has_conflict = False
            evidence.conflict_level = ConflictLevel.NONE

        return evidence

    def _assess_conflict_level(self, evidence: FieldEvidence) -> ConflictLevel:
        """Determine conflict severity from variant structure."""
        consensus = evidence.consensus_variant
        if not consensus or len(evidence.variants) <= 1:
            return ConflictLevel.NONE

        # Find the strongest dissenting variant
        max_dissent_tier = "D"
        for v in evidence.variants[1:]:  # skip consensus
            if v.best_tier in ("S", "A"):
                max_dissent_tier = v.best_tier
            elif v.best_tier == "B" and max_dissent_tier not in ("S", "A"):
                max_dissent_tier = "B"

        # Critical field escalation
        if evidence.is_critical_field and max_dissent_tier in ("S", "A"):
            return ConflictLevel.CRITICAL

        # Tier-based
        if max_dissent_tier in ("S", "A"):
            return ConflictLevel.STRONG
        if max_dissent_tier == "B":
            return ConflictLevel.MODERATE
        return ConflictLevel.WEAK

    def compute_consensus(
        self, field_name: str, base_verdict: str,
    ) -> EvidenceConsensusResult:
        """Compute evidence consensus for a claim verification.

        Args:
            field_name: GT field being verified
            base_verdict: existing fact verdict from verify_claim (supported/contradicted/...)

        Returns:
            EvidenceConsensusResult with strength level and full evidence snapshot.
        """
        evidence = self.build_field_evidence(field_name)
        return self._consensus_from_evidence(evidence, base_verdict)

    def _consensus_from_evidence(
        self, evidence: FieldEvidence, base_verdict: str,
    ) -> EvidenceConsensusResult:
        """Derive EvidenceConsensusResult from FieldEvidence."""
        # v1 GT → unavailable
        if evidence.gt_schema == "v1":
            level = EvidenceStrengthLevel.UNAVAILABLE
        elif evidence.total_sources == 0:
            level = EvidenceStrengthLevel.INSUFFICIENT
        elif evidence.has_conflict:
            level = EvidenceStrengthLevel.DISPUTED
        else:
            # Determine strength from agreement + tier + source count
            level = self._compute_strength_level(evidence)

        # Build variant summaries for JSON
        variant_dicts = []
        for v in evidence.variants:
            variant_dicts.append({
                "normalized_value": v.normalized_value,
                "raw_values": v.raw_values,
                "source_count": v.source_count,
                "weighted_score": v.weighted_score,
                "best_tier": v.best_tier,
                "tiers": v.tiers,
            })

        return EvidenceConsensusResult(
            field_name=evidence.field_name,
            base_verdict=base_verdict,
            evidence_strength_level=level,
            agreement_ratio=evidence.agreement_ratio,
            total_sources=evidence.total_sources,
            supporting_sources=evidence.consensus_variant.source_count if evidence.consensus_variant else 0,
            best_tier=evidence.best_tier,
            best_source=evidence.best_source,
            consensus_value=evidence.consensus_value,
            has_conflict=evidence.has_conflict,
            conflict_level=evidence.conflict_level,
            value_variants=variant_dicts,
            excluded_sources=evidence.excluded_sources,
            notes=evidence.notes,
        )

    def _compute_strength_level(self, evidence: FieldEvidence) -> EvidenceStrengthLevel:
        """Map evidence quality to strength level."""
        ar = evidence.weighted_agreement_ratio
        bt = evidence.best_tier
        ns = evidence.total_sources

        # Single source rules (P0-8 degradation)
        if ns == 1:
            if bt in ("S", "A"):
                src_type = evidence.best_source.get("source_type", "other") if evidence.best_source else "other"
                has_evidence = bool(
                    (evidence.best_source or {}).get("evidence_text", "").strip()
                ) if evidence.best_source else False
                if src_type in ("official_site", "official_report", "regulatory") and has_evidence:
                    return EvidenceStrengthLevel.STRONG
                return EvidenceStrengthLevel.MODERATE
            if bt == "B":
                return EvidenceStrengthLevel.MODERATE
            return EvidenceStrengthLevel.WEAK

        # Multi-source rules
        if ar >= 0.70 and bt in ("S", "A") and ns >= 2:
            return EvidenceStrengthLevel.STRONG
        if ar >= 0.50 and bt in ("A", "B"):
            return EvidenceStrengthLevel.MODERATE
        return EvidenceStrengthLevel.WEAK

    def cross_validate_claim(
        self, field_name: str, base_verdict: str,
    ) -> EvidenceConsensusResult:
        """Cross-validate a single claim against multi-source evidence."""
        return self.compute_consensus(field_name, base_verdict)
