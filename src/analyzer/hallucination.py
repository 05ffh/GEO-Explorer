import re
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.query_result import QueryResult
from src.models.ground_truth import GroundTruthVersion
from src.models.hallucination import HallucinationResult
from src.schemas.ground_truth import GT_FIELD_LEVELS


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
class Claim:
    field: str
    claim_text: str
    context: str
    confidence: float


@dataclass
class ClaimVerification:
    verdict: str  # correct / incorrect / partial / unsupported / uncertain
    error_type: str | None
    severity: str
    gt_value: str
    similarity_score: float | None
    explanation: str
    needs_human_review: bool


# Keywords that signal a factual claim about each GT field
FIELD_SIGNALS = {
    "industry": ["行业", "领域", "属于", "产业", "垂直"],
    "category": ["品类", "类别", "类型", "细分", "分类"],
    "positioning": ["定位", "核心", "主打", "专注于", "致力于"],
    "target_users": ["用户", "客户", "消费者", "面向", "人群", "服务"],
    "core_products": ["产品", "提供", "推出", "上线", "包含"],
    "core_features": ["功能", "特性", "特点", "能力", "支持"],
    "key_differentiators": ["优势", "不同", "区别", "特色", "独特", "差异化"],
    "target_competitors": ["竞品", "竞争", "对手", "替代", "同行"],
    "official_name": ["公司", "企业", "品牌", "集团", "平台"],
    "core_scenarios": ["场景", "用途", "应用", "解决", "需求"],
    "forbidden_claims": ["领先", "第一", "最大", "最好", "唯一", "最强", "最"],
}


def _tokenize(text: str) -> set[str]:
    """Extract tokens using punctuation-splitting + character n-grams for Chinese."""
    text = text.lower()
    # Split on punctuation
    phrases = re.split(r'[，。、；：！？\s\n\(\)（）\[\]【】""''/，,!?;:\-]+', text)
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

    def extract_claims(self, response: str) -> list[Claim]:
        """Extract sentences that make factual claims about specific GT fields."""
        claims = []
        sentences = re.split(r'[。\n]+', response)

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
                    claims.append(Claim(
                        field=field_name,
                        claim_text=fragment[:150],
                        context=response[ctx_start:ctx_end] if ctx_start < ctx_end else sent[:200],
                        confidence=0.6 + (0.1 * len(matched_kw)),
                    ))
                    break

        return claims

    def verify_claim(self, claim: Claim, gt_json: dict) -> dict:
        """Verify claim against GT with error type classification and human review flag."""
        gt_value = gt_json.get(claim.field)
        field_level = GT_FIELD_LEVELS.get(claim.field, "P1")

        if not gt_value:
            return {
                "verdict": "uncertain", "severity": field_level,
                "error_type": None, "needs_human_review": False,
                "reason": "GT field not defined, cannot verify",
            }

        gt_str = str(gt_value) if not isinstance(gt_value, list) else " ".join(gt_value)
        claim_tokens = _tokenize(claim.claim_text)
        gt_tokens = _tokenize(gt_str)

        if not claim_tokens or not gt_tokens:
            return {"verdict": "uncertain", "severity": field_level,
                    "error_type": None, "needs_human_review": False,
                    "reason": "Insufficient tokens", "ai_claim": claim.claim_text,
                    "ground_truth_value": gt_str}

        overlap = claim_tokens & gt_tokens
        claim_coverage = len(overlap) / len(claim_tokens) if claim_tokens else 0
        gt_coverage = len(overlap) / len(gt_tokens) if gt_tokens else 0
        similarity_score = (claim_coverage + gt_coverage) / 2

        # Correct: strong overlap both ways
        if gt_coverage >= 0.3 and claim_coverage >= 0.2:
            return {
                "verdict": "correct", "severity": field_level,
                "error_type": None, "needs_human_review": False,
                "similarity_score": round(similarity_score, 3),
                "reason": f"Token match: claim={claim_coverage:.0%} gt={gt_coverage:.0%}",
                "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
            }

        # Determine error type
        extra_tokens = claim_tokens - gt_tokens
        forbidden = {"领先", "第一", "最大", "最好", "唯一", "最强", "顶级", "绝对"}
        hit_forbidden = [t for t in extra_tokens if t in forbidden]

        if hit_forbidden:
            return {
                "verdict": "incorrect", "severity": "P0",
                "error_type": "overclaim", "needs_human_review": True,
                "similarity_score": round(similarity_score, 3),
                "reason": f"Forbidden claim: {hit_forbidden}",
                "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
            }

        if extra_tokens and gt_coverage < 0.15:
            error_type = _classify_error_type(claim.field, claim.claim_text, gt_str)
            needs_review = field_level == "P0" or claim.field in (
                "official_name", "category", "positioning")
            return {
                "verdict": "incorrect", "severity": field_level,
                "error_type": error_type, "needs_human_review": needs_review,
                "similarity_score": round(similarity_score, 3),
                "reason": f"Tokens not in GT: {sorted(extra_tokens)[:5]}",
                "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
            }

        # Partial / uncertain
        return {
            "verdict": "uncertain", "severity": field_level,
            "error_type": None, "needs_human_review": False,
            "similarity_score": round(similarity_score, 3) if overlap else None,
            "reason": "Partial match — needs human review" if overlap else "No match",
            "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
        }

    async def detect(
        self, query_result: QueryResult, gt: GroundTruthVersion, db: AsyncSession,
    ) -> list[HallucinationResult]:
        claims = self.extract_claims(query_result.answer_text)
        gt_json = gt.ground_truth_json
        results = []

        for claim in claims:
            verification = self.verify_claim(claim, gt_json)
            h = HallucinationResult(
                brand_id=query_result.brand_id,
                query_result_id=query_result.id,
                ground_truth_version_id=gt.id,
                field_name=claim.field,
                field_level=GT_FIELD_LEVELS.get(claim.field, "P1"),
                severity=verification.get("severity", "P1"),
                verdict=verification["verdict"],
                ai_claim=verification.get("ai_claim", claim.claim_text),
                ground_truth_value=verification.get("ground_truth_value", ""),
            )
            results.append(h)
        return results


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
