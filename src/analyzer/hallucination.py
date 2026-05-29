import re
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult
from src.models.ground_truth import GroundTruthVersion
from src.models.hallucination import HallucinationResult
from src.schemas.ground_truth import GT_FIELD_LEVELS


@dataclass
class Claim:
    field: str
    claim_text: str
    context: str
    confidence: float


class HallucinationDetector:
    FIELD_EXTRACTORS = {
        "industry": [
            r'(?:属于|是[一]?[个家]?)([^，。\n]{4,40})(?:行业|领域|公司|企业|平台|工具)',
        ],
        "positioning": [
            r'(?:定位[是为]|核心[是为]|主要[是为]|是[一]?[个家]?)([^，。\n]{4,60})(?:平台|工具|公司|产品|服务|方案)',
        ],
        "category": [
            r'(?:提供|做|专注[于]?)([^，。\n]{4,40})(?:服务|产品|业务|功能|方案)',
        ],
        "target_users": [
            r'(?:面向|服务[于]?|适合|针对|用户[是为])([^，。\n]{4,40})',
        ],
        "key_differentiators": [
            r'(?:不同于|优势[是在于]|特色[是在于]|区别于|不同[在于])([^，。\n]{4,60})',
        ],
        "core_products": [
            r'(?:核心产品|主要产品|产品[包括有为])([^，。\n]{4,60})',
        ],
        "target_competitors": [
            r'(?:竞品|竞争[对手]|替代[方案品])([^，。\n]{4,40})',
        ],
    }

    def extract_claims(self, response: str) -> list[Claim]:
        claims = []
        for field_name, patterns in self.FIELD_EXTRACTORS.items():
            for pat in patterns:
                for match in re.finditer(pat, response):
                    ctx = response[
                        max(0, match.start() - 30):min(len(response), match.end() + 50)
                    ]
                    claims.append(Claim(
                        field=field_name, claim_text=match.group(0),
                        context=ctx, confidence=0.7,
                    ))
        return claims

    def verify_claim(self, claim: Claim, gt_json: dict) -> dict:
        gt_value = gt_json.get(claim.field)
        field_level = GT_FIELD_LEVELS.get(claim.field, "P1")

        if not gt_value:
            return {
                "verdict": "not_mentioned", "severity": field_level,
                "reason": "GT field not defined",
            }

        gt_str = str(gt_value) if not isinstance(gt_value, list) else " ".join(gt_value)

        # Check if any significant word from GT appears in claim (fuzzy match)
        gt_words = set(gt_str.lower().replace("、", " ").replace("，", " ").split())
        claim_lower = claim.claim_text.lower()
        matches = sum(1 for w in gt_words if len(w) >= 2 and w in claim_lower)

        if matches >= 2 or gt_str.lower()[:30] in claim_lower:
            return {
                "verdict": "correct", "severity": field_level,
                "reason": f"Claim matches GT: {gt_str[:50]}",
                "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
            }

        # Check for contradiction: hard-coded specific checks
        if any(kw in claim.claim_text.lower() for kw in ["营销", "CRM", "ERP"]) and \
           not any(kw in gt_str.lower() for kw in ["营销", "CRM", "ERP"]):
            return {
                "verdict": "incorrect", "severity": field_level,
                "reason": f"Claim contradicts GT. Claim: '{claim.claim_text[:80]}', GT: '{gt_str[:80]}'",
                "ai_claim": claim.claim_text, "ground_truth_value": gt_str,
            }

        return {
            "verdict": "uncertain", "severity": field_level,
            "reason": "Cannot determine match — needs human review",
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
                severity=verification["severity"],
                verdict=verification["verdict"],
                ai_claim=claim.claim_text,
                ground_truth_value=verification.get("ground_truth_value", ""),
            )
            results.append(h)
        return results
