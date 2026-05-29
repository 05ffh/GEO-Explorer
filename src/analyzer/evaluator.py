from enum import Enum
from dataclasses import dataclass


class Verdict(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"
    UNCERTAIN = "uncertain"
    NOT_MENTIONED = "not_mentioned"


@dataclass
class FieldEvaluation:
    field: str
    verdict: Verdict
    evidence: str
    reason: str
    ai_claim: str = ""
    ground_truth_value: str = ""
    coverage_rate: float = 1.0


def _tokenize(text: str) -> set[str]:
    """Extract meaningful tokens from Chinese text."""
    # Split on punctuation and whitespace
    import re
    tokens = re.split(r'[，。、；：！？\s\n\(\)（）\[\]【】""''/]+', text.lower())
    return {t.strip() for t in tokens if len(t.strip()) >= 2}


def evaluate_field(field: str, gt_value, ai_text: str) -> FieldEvaluation:
    if gt_value is None or gt_value == "":
        return FieldEvaluation(
            field=field, verdict=Verdict.NOT_MENTIONED,
            evidence="", reason="GT field is empty", ground_truth_value="",
        )

    gt_str = str(gt_value) if not isinstance(gt_value, list) else " ".join(gt_value)

    if not isinstance(gt_value, list):
        # Try exact substring match first
        if gt_str.lower() in ai_text.lower():
            return FieldEvaluation(
                field=field, verdict=Verdict.CORRECT,
                evidence=ai_text[:200], reason="Exact match in response",
                ai_claim=gt_str, ground_truth_value=gt_str,
            )

        # Fuzzy token-based match for Chinese text
        gt_tokens = _tokenize(gt_str)
        ai_tokens = _tokenize(ai_text)
        if gt_tokens:
            overlap = gt_tokens & ai_tokens
            rate = len(overlap) / len(gt_tokens)
            if rate >= 0.5:
                return FieldEvaluation(
                    field=field, verdict=Verdict.PARTIAL,
                    evidence=ai_text[:200],
                    reason=f"{len(overlap)}/{len(gt_tokens)} tokens matched ({rate:.0%})",
                    ai_claim=", ".join(sorted(overlap)[:5]),
                    ground_truth_value=gt_str,
                    coverage_rate=rate,
                )
            elif rate >= 0.2:
                return FieldEvaluation(
                    field=field, verdict=Verdict.PARTIAL,
                    evidence=ai_text[:200],
                    reason=f"Partial token match ({rate:.0%})",
                    ground_truth_value=gt_str,
                    coverage_rate=rate,
                )

        return FieldEvaluation(
            field=field, verdict=Verdict.NOT_MENTIONED,
            evidence="", reason=f"No token match for '{gt_str[:50]}'",
            ground_truth_value=gt_str,
        )

    if isinstance(gt_value, list):
        covered = [item for item in gt_value if str(item).lower() in ai_text.lower()]
        # Also check fuzzy for list items
        if not covered:
            ai_tokens_set = _tokenize(ai_text)
            covered = [item for item in gt_value
                       if _tokenize(str(item)) & ai_tokens_set]
        rate = len(covered) / len(gt_value) if gt_value else 1.0
        if rate >= 0.8:
            v = Verdict.CORRECT
        elif rate >= 0.4:
            v = Verdict.PARTIAL
        elif rate > 0:
            v = Verdict.PARTIAL
        else:
            v = Verdict.NOT_MENTIONED
        return FieldEvaluation(
            field=field, verdict=v, evidence=ai_text[:200],
            reason=f"{len(covered)}/{len(gt_value)} items covered",
            ai_claim=", ".join(covered),
            ground_truth_value=", ".join(gt_value),
            coverage_rate=rate,
        )

    return FieldEvaluation(
        field=field, verdict=Verdict.UNCERTAIN, evidence=ai_text[:200],
        reason="Unable to determine — needs human review",
        ground_truth_value=gt_str,
    )
