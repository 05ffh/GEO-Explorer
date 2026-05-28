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


def evaluate_field(field: str, gt_value, ai_text: str) -> FieldEvaluation:
    if gt_value is None or gt_value == "":
        return FieldEvaluation(
            field=field, verdict=Verdict.NOT_MENTIONED,
            evidence="", reason="GT field is empty", ground_truth_value="",
        )

    gt_str = str(gt_value) if not isinstance(gt_value, list) else " ".join(gt_value)

    if not isinstance(gt_value, list):
        if gt_str.lower() in ai_text.lower():
            return FieldEvaluation(
                field=field, verdict=Verdict.CORRECT,
                evidence=ai_text[:200], reason="Exact match in response",
                ai_claim=gt_str, ground_truth_value=gt_str,
            )
        else:
            return FieldEvaluation(
                field=field, verdict=Verdict.NOT_MENTIONED,
                evidence="", reason=f"'{gt_str[:50]}' not found in response",
                ground_truth_value=gt_str,
            )

    if isinstance(gt_value, list):
        covered = [item for item in gt_value if str(item).lower() in ai_text.lower()]
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
