import re
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.query_result import QueryResult
from src.models.ground_truth import GroundTruthVersion
from src.models.hallucination import HallucinationResult
from src.schemas.ground_truth import GT_FIELD_LEVELS
from src.analyzer.claim_taxonomy import classify_claim_nature
from src.analyzer.enums import ClaimNature, HallucinationVerdict
from src.services.evidence_cross_validator import EvidenceCrossValidator, EvidenceStrengthLevel, ConflictLevel


# ── Expanded verdict states (P0-6) ──────────────────────────────────────────
# supported: GT supports the claim
# contradicted: claim conflicts with GT
# unsupported: GT does not cover this claim
# not_about_brand: response is not about the target brand
# generic_statement: generic advice, not a brand claim
# template_invalid: template had unresolved variables
# gt_insufficient: GT does not have enough data to verify
# ambiguous: claim is semantically unclear
# not_checkable: claim cannot be fact-checked

SERIOUS_CONTROVERSY = {HallucinationVerdict.CONTRADICTED, HallucinationVerdict.UNSUPPORTED}
NON_HALLUCINATION = {HallucinationVerdict.NOT_ABOUT_BRAND, HallucinationVerdict.GENERIC_STATEMENT, HallucinationVerdict.TEMPLATE_INVALID, HallucinationVerdict.NOT_CHECKABLE}

_UNRESOLVED_VAR_RE = re.compile(r"\{[^{}]+\}")


def check_template_render_status(
    template_text: str,
    brand_name: str = "",
    brand_industry: str = "",
    gt_json: dict | None = None,
) -> str:
    """Check whether a template can be fully rendered.

    Returns 'ok' if all variables resolve, 'missing_variable' otherwise.
    """
    _GT_VAR_MAP = {
        "{品类}": "category",
        "{竞品}": "target_competitors",
        "{场景}": "core_scenarios",
        "{目标用户}": "target_users",
    }
    text = template_text
    text = text.replace("{品牌}", brand_name)
    text = text.replace("{行业}", brand_industry or "")
    gt = gt_json or {}
    for var, gt_key in _GT_VAR_MAP.items():
        val = gt.get(gt_key, "")
        if isinstance(val, list):
            val = "、".join(str(v) for v in val)
        text = text.replace(var, str(val) if val else var)
    remaining = _UNRESOLVED_VAR_RE.findall(text)
    return "missing_variable" if remaining else "ok"


HALLUCINATION_ERROR_TYPES = {
    "identity_error": "品牌身份错误",
    "category_error": "行业/品类错误",
    "positioning_error": "定位描述错误",
    "feature_error": "功能/产品描述错误",
    "competitor_confusion": "竞品混淆",
    "unsupported_claim": "无来源支撑的声明",
    "outdated_claim": "过时信息",
    "overclaim": "夸大声明",
    "negative_hallucination": "遗漏关键信息",
}


@dataclass
class BrandRelevanceResult:
    relevance: str  # brand_centric | brand_mentioned | category_general | irrelevant
    confidence: float
    evidence: list[str] = field(default_factory=list)
    should_extract_brand_claims: bool = False


@dataclass
class Claim:
    field: str
    claim_text: str
    context: str
    confidence: float
    subject_type: str = "unknown"   # target_brand | competitor | category | generic | unknown
    predicate_type: str = "other"   # identity | industry | product | positioning | target_user | scenario | competitor | reputation | recommendation | other
    checkable: bool = False
    source_sentence: str = ""
    claim_nature: str = "unknown"            # fact | opinion | speculation | unknown (ClaimNature enum value)
    claim_nature_confidence: float = 0.0     # classifier confidence
    claim_nature_reason: str = ""            # classifier explanation
    claim_nature_signals: list = field(default_factory=list)       # matched signal words
    claim_nature_signal_strength: str = ""   # strong | weak | mixed | none
    claim_nature_needs_hr: bool = False      # classifier-flagged for human review


@dataclass
class ClaimVerification:
    verdict: str  # supported | contradicted | unsupported | not_about_brand | generic_statement | template_invalid | gt_insufficient | ambiguous | not_checkable
    error_type: str | None
    severity: str
    gt_value: str
    similarity_score: float | None
    explanation: str
    needs_human_review: bool


# Keywords that signal a factual claim about each GT field
FIELD_SIGNALS = {
    "industry": ["行业", "领域", "属于", "产业", "垂直", "是一家"],
    "category": ["品类", "类别", "类型", "细分", "分类"],
    "positioning": ["定位", "核心", "主打", "专注于", "致力于"],
    "target_users": ["用户", "客户", "消费者", "面向", "人群", "服务"],
    "core_products": ["产品", "提供", "推出", "上线", "包含"],
    "core_features": ["功能", "特性", "特点", "能力", "支持"],
    "key_differentiators": ["优势", "不同", "区别", "特色", "独特", "差异化"],
    "target_competitors": ["竞品", "竞争", "对手", "替代", "同行"],
    "official_name": ["公司", "企业", "品牌", "集团", "平台", "名称", "官方", "全称", "名为", "称为", "叫做"],
    "core_scenarios": ["场景", "用途", "应用", "解决", "需求"],
    "forbidden_claims": ["领先", "第一", "最大", "最好", "唯一", "最强", "最"],
}


def _tokenize(text: str) -> set[str]:
    """Extract tokens using punctuation-splitting + character n-grams for Chinese."""
    text = text.lower()
    # Split on punctuation
    phrases = re.split(r'[，。、；：！？\s\n\(\)（）\[\]【】""''/，,!?;:\\-]+', text)
    phrases = [p.strip() for p in phrases if len(p.strip()) >= 2]
    tokens = set()
    for phrase in phrases:
        tokens.add(phrase)
        # 2-char and 3-char sliding windows for Chinese fuzzy matching
        if len(phrase) >= 2:
            for i in range(len(phrase) - 1):
                tokens.add(phrase[i:i+2])
        if len(phrase) >= 3:
            for i in range(len(phrase) - 2):
                tokens.add(phrase[i:i+3])
    return tokens


class HallucinationDetector:
    """Detect factual claims in AI responses and verify against Ground Truth."""

    def _classify_relevance(self, response: str, brand_name: str, gt_json: dict) -> BrandRelevanceResult:
        """Classify whether an AI response is about the target brand (P0-4)."""
        official = str(gt_json.get("official_name", ""))
        industry = str(gt_json.get("industry", ""))
        evidence = []

        # Build brand name variants: full name, short name (before parens), official name
        _brand_variants = {brand_name, official}
        _short = re.split(r'[（(]', brand_name)[0].strip()
        if _short:
            _brand_variants.add(_short)
        _short_o = re.split(r'[（(]', official)[0].strip()
        if _short_o:
            _brand_variants.add(_short_o)
        _brand_variants.discard("")

        brand_mentions = any(v in response for v in _brand_variants)
        if brand_mentions:
            evidence.append(f"品牌名出现: {brand_name}")

        # Count sentences where brand is clearly the subject
        sentences = re.split(r'[。\n]+', response)
        brand_subject_count = 0
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            for _v in _brand_variants:
                if _v in sent and sent.index(_v) < min(len(sent) / 3, 20):
                    brand_subject_count += 1
                    break

        # If brand is the subject of multiple sentences, it's brand_centric
        if brand_subject_count >= 2:
            return BrandRelevanceResult(
                relevance="brand_centric", confidence=0.9, evidence=evidence,
                should_extract_brand_claims=True,
            )

        # If brand is mentioned at least once as subject
        if brand_subject_count >= 1 or (brand_mentions and len(sentences) <= 5):
            return BrandRelevanceResult(
                relevance="brand_centric" if brand_subject_count > 0 else "brand_mentioned",
                confidence=0.7, evidence=evidence,
                should_extract_brand_claims=brand_subject_count > 0,
            )

        # Check for category/industry-level discussion (not about brand)
        industry_words = ["行业", "品类", "工具", "平台", "推荐", "选择"]
        if any(w in response for w in industry_words):
            return BrandRelevanceResult(
                relevance="category_general", confidence=0.6,
                evidence=["回答讨论行业/品类而非特定品牌"],
                should_extract_brand_claims=False,
            )

        return BrandRelevanceResult(
            relevance="irrelevant", confidence=0.5,
            evidence=["未找到品牌相关信号"],
            should_extract_brand_claims=False,
        )

    def _infer_subject_type(self, claim_text: str, brand_name: str, gt_json: dict) -> str:
        """Infer whether a claim is about the target brand, a competitor, or generic."""
        official = str(gt_json.get("official_name", ""))
        _variants = {brand_name, official}
        _s = re.split(r'[（(]', brand_name)[0].strip()
        if _s: _variants.add(_s)
        _s2 = re.split(r'[（(]', official)[0].strip()
        if _s2: _variants.add(_s2)
        _variants.discard("")
        if any(v in claim_text for v in _variants):
            return "target_brand"
        competitors = gt_json.get("target_competitors", [])
        for comp in (competitors if isinstance(competitors, list) else []):
            if str(comp) in claim_text:
                return "competitor"
        return "generic"

    def extract_claims(self, response: str, brand_name: str = "", gt_json: dict | None = None) -> list[Claim]:
        """Extract sentences that make factual claims about specific GT fields."""
        claims = []
        sentences = re.split(r'[。\n]+', response)
        gt = gt_json or {}

        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 10:
                continue

            sent_lower = sent.lower()
            for field_name, keywords in FIELD_SIGNALS.items():
                matched_kw = [kw for kw in keywords if kw in sent_lower]
                if not matched_kw:
                    continue

                for kw in matched_kw:
                    idx = sent_lower.find(kw)
                    start = max(0, idx - 20)
                    end = min(len(sent), idx + len(kw) + 40)
                    fragment = sent[start:end].strip()

                    ctx_start = max(0, idx - 40)
                    ctx_end = min(len(response), response.lower().find(sent_lower) + idx + len(kw) + 60)

                    subject_type = self._infer_subject_type(sent, brand_name, gt) if brand_name else "unknown"
                    predicate_type = _infer_predicate_type(field_name)
                    checkable = subject_type in ("target_brand", "competitor")

                    # P2-1: Classify claim nature (fact/opinion/speculation)
                    nature_result = classify_claim_nature(fragment, predicate_type)

                    claims.append(Claim(
                        field=field_name,
                        claim_text=fragment[:150],
                        context=response[ctx_start:ctx_end] if ctx_start < ctx_end else sent[:200],
                        confidence=0.6 + (0.1 * len(matched_kw)),
                        subject_type=subject_type,
                        predicate_type=predicate_type,
                        checkable=checkable,
                        source_sentence=sent[:300],
                        claim_nature=nature_result.claim_nature.value,
                        claim_nature_confidence=nature_result.confidence,
                        claim_nature_reason=nature_result.reason,
                        claim_nature_signals=nature_result.matched_signals,
                        claim_nature_signal_strength=nature_result.signal_strength,
                        claim_nature_needs_hr=nature_result.needs_human_review,
                    ))
                    break

        return claims

    def verify_claim(self, claim: Claim, gt_json: dict) -> dict:
        """Verify claim against GT with expanded verdict states (P0-6).

        P2-1: claim_nature-aware — OPINION defaults to not_checkable (does not
        enter fact accuracy); SPECULATION gets independent risk tiering.
        """
        field_level = GT_FIELD_LEVELS.get(claim.field, "P1")
        claim_nature = getattr(claim, "claim_nature", "unknown")

        def _evidence(path: str, **kw) -> dict:
            return {"decision_path": path, "field": claim.field,
                    "field_level": field_level, "subject_type": claim.subject_type, **kw}

        # Non-checkable claims
        if not claim.checkable:
            if claim.subject_type == "generic":
                return {"verdict": HallucinationVerdict.GENERIC_STATEMENT, "severity": "Info",
                        "error_type": None, "needs_human_review": False,
                        "reason": "Generic statement, not a brand-specific claim",
                        "ai_claim": claim.claim_text, "ground_truth_value": "",
                        "evidence": _evidence("not_checkable:generic")}
            if claim.subject_type == "competitor":
                return {"verdict": HallucinationVerdict.NOT_CHECKABLE, "severity": "Info",
                        "error_type": None, "needs_human_review": False,
                        "reason": "Claim about competitor, not target brand",
                        "ai_claim": claim.claim_text, "ground_truth_value": "",
                        "evidence": _evidence("not_checkable:competitor")}
            return {"verdict": HallucinationVerdict.NOT_CHECKABLE, "severity": "Info",
                    "error_type": None, "needs_human_review": False,
                    "reason": f"Subject type '{claim.subject_type}' not checkable against brand GT",
                    "ai_claim": claim.claim_text, "ground_truth_value": "",
                    "evidence": _evidence("not_checkable:unknown_subject")}

        # P2-1: OPINION claims — don't enter fact accuracy contradiction
        if claim_nature == "opinion":
            return self._verify_opinion_claim(claim, gt_json, _evidence)

        gt_value = gt_json.get(claim.field)
        if not gt_value:
            return {"verdict": HallucinationVerdict.GT_INSUFFICIENT, "severity": "Info",
                    "error_type": None, "needs_human_review": False,
                    "reason": f"GT field '{claim.field}' not defined, cannot verify",
                    "ai_claim": claim.claim_text, "ground_truth_value": "",
                    "evidence": _evidence("gt_insufficient:field_missing")}

        gt_str = str(gt_value) if not isinstance(gt_value, list) else " ".join(gt_value)

        # Pre-check: literal substring containment
        claim_lower = claim.claim_text.lower()
        gt_lower = gt_str.lower()
        if gt_lower and len(gt_lower) >= 2:
            if gt_lower in claim_lower or claim_lower in gt_lower:
                return {"verdict": HallucinationVerdict.SUPPORTED, "severity": field_level,
                        "error_type": None, "needs_human_review": False,
                        "similarity_score": 1.0,
                        "reason": "Exact string match in claim",
                        "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
                        "evidence": _evidence("literal_substring_match", similarity_score=1.0)}

        claim_tokens = _tokenize(claim.claim_text)
        gt_tokens = _tokenize(gt_str)

        if not claim_tokens or not gt_tokens:
            return {"verdict": HallucinationVerdict.AMBIGUOUS, "severity": "Info",
                    "error_type": None, "needs_human_review": False,
                    "reason": "Insufficient tokens for comparison",
                    "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
                    "evidence": _evidence("ambiguous:no_tokens")}

        overlap = claim_tokens & gt_tokens
        claim_coverage = len(overlap) / len(claim_tokens) if claim_tokens else 0
        gt_coverage = len(overlap) / len(gt_tokens) if gt_tokens else 0
        similarity_score = (claim_coverage + gt_coverage) / 2
        extra_tokens = claim_tokens - gt_tokens
        missing_tokens = gt_tokens - claim_tokens

        # Near-miss detection for short identity fields
        _identity_fields = {"official_name", "industry", "category"}
        if claim.field in _identity_fields and gt_coverage >= 0.3 and claim_coverage >= 0.2:
            claim_clean = re.sub(r'[^a-zA-Z0-9一-鿿]', '', claim.claim_text.lower())
            gt_clean = re.sub(r'[^a-zA-Z0-9一-鿿]', '', gt_str.lower())
            if gt_clean not in claim_clean and claim_clean not in gt_clean \
               and max(len(gt_clean), len(claim_clean)) <= 50:
                from difflib import SequenceMatcher
                char_sim = SequenceMatcher(None, claim_clean, gt_clean).ratio()
                if char_sim < 0.85:
                    return {"verdict": HallucinationVerdict.CONTRADICTED, "severity": "P0",
                            "error_type": "identity_error" if claim.field == "official_name"
                            else "category_error",
                            "needs_human_review": True,
                            "similarity_score": round(similarity_score, 3),
                            "reason": (
                                f"Near-miss identity: n-gram overlap high but "
                                f"char similarity {char_sim:.2f} suggests contradiction"
                            ),
                            "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
                            "evidence": _evidence("near_miss_identity",
                                similarity_score=round(similarity_score, 3),
                                char_similarity=round(char_sim, 3),
                                overlap_tokens=sorted(overlap)[:5],
                                extra_tokens=sorted(extra_tokens)[:5])}

        # Supported: strong overlap both ways
        if gt_coverage >= 0.3 and claim_coverage >= 0.2:
            return {"verdict": HallucinationVerdict.SUPPORTED, "severity": field_level,
                    "error_type": None, "needs_human_review": False,
                    "similarity_score": round(similarity_score, 3),
                    "reason": f"Token match: claim={claim_coverage:.0%} gt={gt_coverage:.0%}",
                    "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
                    "evidence": _evidence("token_match",
                        claim_coverage=round(claim_coverage, 3),
                        gt_coverage=round(gt_coverage, 3),
                        similarity_score=round(similarity_score, 3),
                        overlap_tokens=sorted(overlap)[:5])}

        # Overclaim / contradicted
        forbidden = {"领先", "第一", "最大", "最好", "唯一", "最强", "顶级", "绝对"}
        hit_forbidden = [t for t in extra_tokens if t in forbidden]

        if hit_forbidden:
            return {"verdict": HallucinationVerdict.CONTRADICTED, "severity": "P0",
                    "error_type": "overclaim", "needs_human_review": True,
                    "similarity_score": round(similarity_score, 3),
                    "reason": f"Forbidden claim: {hit_forbidden}",
                    "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
                    "evidence": _evidence("forbidden_claim",
                        forbidden_tokens=hit_forbidden,
                        similarity_score=round(similarity_score, 3))}

        if extra_tokens and gt_coverage < 0.15:
            error_type = _classify_error_type(claim.field, claim.claim_text, gt_str)
            needs_review = field_level == "P0" or claim.field in (
                "official_name", "category", "positioning")
            severity = "P0" if field_level == "P0" and claim.field in (
                "official_name", "industry", "category", "core_products") else field_level
            return {"verdict": HallucinationVerdict.CONTRADICTED, "severity": severity,
                    "error_type": error_type, "needs_human_review": needs_review,
                    "similarity_score": round(similarity_score, 3),
                    "reason": f"Tokens not in GT: {sorted(extra_tokens)[:5]}",
                    "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
                    "evidence": _evidence("contradicted:extra_tokens",
                        error_type=error_type,
                        claim_coverage=round(claim_coverage, 3),
                        gt_coverage=round(gt_coverage, 3),
                        similarity_score=round(similarity_score, 3),
                        extra_tokens=sorted(extra_tokens)[:5],
                        missing_tokens=sorted(missing_tokens)[:5])}

        # Unsupported / ambiguous
        if overlap:
            return {"verdict": HallucinationVerdict.UNSUPPORTED, "severity": field_level,
                    "error_type": None, "needs_human_review": False,
                    "similarity_score": round(similarity_score, 3),
                    "reason": "Partial match — GT cannot fully confirm",
                    "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
                    "evidence": _evidence("unsupported:partial_match",
                        claim_coverage=round(claim_coverage, 3),
                        gt_coverage=round(gt_coverage, 3),
                        similarity_score=round(similarity_score, 3),
                        overlap_tokens=sorted(overlap)[:5])}

        return {"verdict": HallucinationVerdict.AMBIGUOUS, "severity": "Info",
                "error_type": None, "needs_human_review": False,
                "reason": "No meaningful overlap with GT",
                "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
                "evidence": _evidence("ambiguous:no_overlap",
                    claim_coverage=round(claim_coverage, 3),
                    gt_coverage=round(gt_coverage, 3))}

    # ── P2-1: OPINION / SPECULATION claim handling ──────────────────────────

    def _verify_opinion_claim(self, claim: Claim, gt_json: dict, _evidence) -> dict:
        """Verify OPINION claim — subjective; don't enter fact accuracy contradiction.

        OPINION claims default to not_checkable / Info.
        Exception: absolute high-risk expressions escalate to P1 and human review.
        """
        # Absolute claim keywords that escalate opinion to risk
        absolute_kw = ["唯一", "第一", "最安全", "100%", "绝对", "官方认证最好",
                       "唯一获得", "唯一通过", "唯一拥有"]
        has_absolute = any(kw in claim.claim_text for kw in absolute_kw)

        # Check if GT has contradictory evidence for the absolute claim
        field_level = GT_FIELD_LEVELS.get(claim.field, "P1")

        if has_absolute:
            # Absolute opinion claims in high-risk fields get elevated severity
            high_risk_fields = {"official_name", "industry", "category",
                                "core_products", "core_features"}
            severity = "P1" if claim.field in high_risk_fields else "P2"
            return {"verdict": HallucinationVerdict.NOT_CHECKABLE, "severity": severity,
                    "error_type": "opinion_absolute_claim",
                    "needs_human_review": True,
                    "reason": f"观点声明包含绝对化表达: {claim.claim_text[:80]}",
                    "ai_claim": claim.claim_text, "ground_truth_value": "",
                    "evidence": _evidence("opinion:absolute_claim",
                        claim_nature="opinion")}

        return {"verdict": HallucinationVerdict.NOT_CHECKABLE, "severity": "Info",
                "error_type": "opinion_claim",
                "needs_human_review": False,
                "reason": "观点类声明，不进入事实准确率判定",
                "ai_claim": claim.claim_text, "ground_truth_value": "",
                "evidence": _evidence("opinion:subjective",
                    claim_nature="opinion")}

    def _adjust_speculation_severity(
        self, verification: dict, claim: Claim) -> dict:
        """Adjust verdict/severity for SPECULATION claims (P2-1).

        SPECULATION is not inherently wrong — risk depends on sources, industry,
        and predicate type. Lowers severity for low-risk speculation;
        elevates for high-risk (financial, regulatory, etc.).
        """
        risk_level = getattr(claim, "claim_nature_reason", "")
        # Extract risk level from claim nature classifier result
        from src.analyzer.claim_taxonomy import HIGH_RISK_PREDICATES

        predicate = getattr(claim, "predicate_type", "other")
        is_high_risk = predicate in HIGH_RISK_PREDICATES

        current_severity = verification.get("severity", "P1")
        current_verdict = verification.get("verdict", HallucinationVerdict.UNSUPPORTED)

        if is_high_risk:
            # Financial/regulatory/health speculation: elevate severity
            if current_verdict in (HallucinationVerdict.CONTRADICTED, HallucinationVerdict.UNSUPPORTED):
                verification["severity"] = "P0" if current_severity == "P0" else "P1"
                verification["needs_human_review"] = True
                verification["error_type"] = f"high_risk_speculation_{predicate}"
                ev = verification.get("evidence", {})
                ev["speculation_risk"] = "high"
                ev["claim_nature"] = "speculation"
                verification["evidence"] = ev
        else:
            # Low/medium risk speculation: lower severity
            if current_verdict == HallucinationVerdict.CONTRADICTED:
                verification["severity"] = "P2"
                verification["error_type"] = "low_risk_speculation"
            elif current_verdict == HallucinationVerdict.UNSUPPORTED and current_severity == "P0":
                verification["severity"] = "P1"

        # Tag verification with claim nature
        ev = verification.get("evidence", {})
        ev["claim_nature"] = "speculation"
        verification["evidence"] = ev
        return verification

    # ── End P2-1 helpers ────────────────────────────────────────────────────

    async def detect(
        self, query_result: QueryResult, gt: GroundTruthVersion, db: AsyncSession,
        brand_name: str = "",
        render_status: str = "ok",
    ) -> list[HallucinationResult]:
        gt_json = gt.get_flat_json() if hasattr(gt, "get_flat_json") else gt.ground_truth_json
        brand = brand_name or str(gt_json.get("official_name", ""))

        # Brand relevance pre-check (P0-4)
        relevance = self._classify_relevance(query_result.answer_text, brand, gt_json)

        # Only extract brand claims for brand_centric responses
        if relevance.relevance not in ("brand_centric", "brand_mentioned"):
            verdict = HallucinationVerdict.NOT_ABOUT_BRAND if relevance.relevance != "category_general" else HallucinationVerdict.GENERIC_STATEMENT
            if render_status != "ok":
                verdict = HallucinationVerdict.TEMPLATE_INVALID
            return [HallucinationResult(
                brand_id=query_result.brand_id,
                query_result_id=query_result.id,
                collection_run_id=query_result.collection_run_id,
                ground_truth_version_id=gt.id,
                field_name="",
                field_level="Info",
                severity="Info",
                verdict=verdict,
                ai_claim=relevance.evidence[0] if relevance.evidence else "",
                ground_truth_value="",
                error_type="",
                claim_type="unknown",
                predicate_type="other",
            )]

        # Extract claims with brand awareness
        claims = self.extract_claims(query_result.answer_text, brand, gt_json)
        results = []

        # P2-2: multi-evidence cross-validator (cached per field)
        evidence_validator = EvidenceCrossValidator(gt)

        for claim in claims:
            verification = self.verify_claim(claim, gt_json)
            # P2-2: compute evidence consensus for this claim
            base_verdict = verification["verdict"]
            try:
                consensus = evidence_validator.cross_validate_claim(
                    claim.field, base_verdict)
                evidence_json = consensus.to_json()
            except Exception:
                evidence_json = None
            # P2-1: Adjust speculation claims — not inherently wrong
            if getattr(claim, "claim_nature", "unknown") == "speculation":
                verification = self._adjust_speculation_severity(verification, claim)
            # P1-6: LLM-as-Judge fallback for borderline n-gram results
            sim = verification.get("similarity_score")
            if sim is not None and 0.05 < sim < 0.35 and claim.checkable:
                try:
                    llm_result = await self._llm_verify_claim(
                        claim, gt_json.get(claim.field), GT_FIELD_LEVELS.get(claim.field, "P1"))
                    if llm_result:
                        verification["llm_verdict"] = llm_result["verdict"]
                        verification["llm_confidence"] = llm_result["confidence"]
                        verification["llm_reasoning"] = llm_result["reasoning"]
                        verification["llm_platform"] = llm_result.get("llm_platform", "")
                except Exception:
                    pass
            reason = verification.get("reason", "")
            # P1-1: attach GT source evidence for contradicted claims
            if verification.get("verdict") == HallucinationVerdict.CONTRADICTED and hasattr(gt, "get_best_source_for_field"):
                best_src = gt.get_best_source_for_field(claim.field, min_tier="B")
                if best_src:
                    reason += f" | GT source: [{best_src.get('tier','?')}] {best_src.get('title','') or best_src.get('url','')}"
            # P1-5: append debug evidence summary
            ev = verification.get("evidence", {})
            if ev:
                path = ev.get("decision_path", "?")
                sim = ev.get("similarity_score")
                parts = [f"path={path}"]
                if sim is not None:
                    parts.append(f"sim={sim:.3f}")
                if "char_similarity" in ev:
                    parts.append(f"char_sim={ev['char_similarity']:.3f}")
                if "overlap_tokens" in ev:
                    parts.append(f"overlap={ev['overlap_tokens'][:3]}")
                if "extra_tokens" in ev:
                    parts.append(f"extra={ev['extra_tokens'][:3]}")
                reason += " | " + " ".join(parts)
            h = HallucinationResult(
                brand_id=query_result.brand_id,
                query_result_id=query_result.id,
                collection_run_id=query_result.collection_run_id,
                ground_truth_version_id=gt.id,
                field_name=claim.field,
                field_level=GT_FIELD_LEVELS.get(claim.field, "P1"),
                severity=verification.get("severity", "P1"),
                verdict=verification["verdict"],
                ai_claim=verification.get("ai_claim", claim.claim_text),
                ground_truth_value=verification.get("ground_truth_value", ""),
                error_type=verification.get("error_type") or "",
                subject_type=claim.subject_type,
                claim_text=claim.claim_text,
                matched_gt_field=claim.field,
                reason=reason,
                claim_type=getattr(claim, "claim_nature", "unknown"),
                predicate_type=getattr(claim, "predicate_type", "other"),
                evidence_consensus_json=evidence_json,
            )
            # Append claim nature debug info to reason
            cn_signals = getattr(claim, "claim_nature_signals", None)
            cn_strength = getattr(claim, "claim_nature_signal_strength", "")
            if cn_signals:
                h.reason += f" | cn_signals={cn_signals[:5]}"
            if cn_strength:
                h.reason += f" | cn_strength={cn_strength}"
            # P2-2: disputed or critical conflict → not hallucination, evidence risk
            if evidence_json:
                strength = evidence_json.get("evidence_strength_level", "")
                cl = evidence_json.get("conflict_level", "none")
                if strength == "disputed" or cl in ("strong_conflict", "critical_conflict"):
                    h.needs_human_review = True
                    if cl == "critical_conflict":
                        h.reason += " | evidence:critical_conflict(GT来源S/A级冲突,需人工裁定)"
                    elif cl == "strong_conflict":
                        h.reason += " | evidence:strong_conflict(GT来源严重分歧)"
                    else:
                        h.reason += " | evidence:disputed(GT证据有争议,不计入AI幻觉)"
            # P2-1: auto-mark for human review on low-confidence / UNKNOWN / high-risk speculation
            if not h.needs_human_review:
                # Check if classifier itself flagged this claim for human review
                c_hr = getattr(claim, "claim_nature_needs_hr", False)
                if c_hr:
                    h.needs_human_review = True
                    h.reason += " | human_review: classifier_flagged"
                else:
                    nc = getattr(claim, "claim_nature_confidence", 1.0)
                    cn = getattr(claim, "claim_nature", "unknown")
                    pt = getattr(claim, "predicate_type", "other")
                    if nc < 0.6 and cn != "unknown":
                        h.needs_human_review = True
                        h.reason += f" | human_review: low_classifier_confidence({nc:.2f})"
                    elif cn == "unknown":
                        h.needs_human_review = True
                        h.reason += " | human_review: unknown_claim_nature"
                    elif cn == "speculation" and pt in ("identity", "core_product", "financial_performance"):
                        h.needs_human_review = True
                        h.reason += f" | human_review: high_risk_speculation({pt})"
            results.append(h)
        return results


    async def _llm_verify_claim(self, claim: Claim, gt_value, field_level: str) -> dict | None:
        """P1-6: Use LLM as judge for semantic consistency when n-gram is ambiguous."""
        import json as _json
        gt_str = str(gt_value) if not isinstance(gt_value, list) else "、".join(str(v) for v in gt_value)
        prompt = (
            "你是一个品牌事实核验专家。请判断以下AI声明是否与Ground Truth一致。\n\n"
            f"字段: {claim.field}\n"
            f"Ground Truth: {gt_str}\n"
            f"AI声明: {claim.claim_text}\n\n"
            "请返回JSON格式（只返回JSON，不要其他内容）:\n"
            '{"verdict": "supported|contradicted|unsupported", '
            '"confidence": 0.0-1.0, "reasoning": "一句话解释"}\n\n'
            "规则:\n"
            "- supported: 声明与GT语义一致或GT包含声明内容\n"
            "- contradicted: 声明明确与GT冲突（如说行业是X但GT说是Y）\n"
            "- unsupported: GT信息不足以判断\n"
        )
        try:
            from src.adapters import get_adapter
            for platform in ["deepseek", "doubao", "kimi"]:
                try:
                    adapter = get_adapter(platform)
                    response = await adapter.query(prompt)
                    if not response.answer_text:
                        continue
                    text = response.answer_text.strip()
                    if "```" in text:
                        text = text.split("```")[1].split("```")[0]
                        if text.startswith("json"):
                            text = text[4:]
                    result = _json.loads(text)
                    if result.get("verdict") in (HallucinationVerdict.SUPPORTED, HallucinationVerdict.CONTRADICTED, HallucinationVerdict.UNSUPPORTED):
                        return {
                            "verdict": result["verdict"],
                            "confidence": float(result.get("confidence", 0.5)),
                            "reasoning": result.get("reasoning", ""),
                            "llm_platform": platform,
                        }
                except Exception:
                    continue
        except Exception:
            pass
        return None


def _infer_predicate_type(field_name: str) -> str:
    """Map GT field name to predicate type."""
    mapping = {
        "official_name": "identity", "industry": "industry", "category": "industry",
        "positioning": "positioning", "target_users": "target_user",
        "core_products": "product", "core_features": "product",
        "key_differentiators": "positioning", "target_competitors": "competitor",
        "core_scenarios": "scenario", "forbidden_claims": "reputation",
    }
    return mapping.get(field_name, "other")


def _classify_error_type(field: str, claim_text: str, gt_str: str) -> str:
    """Classify hallucination error type based on field and content."""
    if field in ("official_name",):
        return "identity_error"
    if field in ("category", "industry"):
        return "category_error"
    if field in ("positioning",):
        return "positioning_error"
    if field in ("core_products", "core_features"):
        return "feature_error"
    if field in ("target_competitors",):
        return "competitor_confusion"
    # Check for overclaim/unsupported patterns
    overclaim_kw = ["领先", "第一", "最大", "最好", "唯一", "最强", "顶级", "绝对"]
    if any(kw in claim_text for kw in overclaim_kw):
        return "overclaim"
    if len(gt_str) < 10:
        return "unsupported_claim"
    return "unsupported_claim"
