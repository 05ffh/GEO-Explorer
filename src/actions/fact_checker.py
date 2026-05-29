import logging

logger = logging.getLogger(__name__)

FORBIDDEN_CLAIMS = ["领先", "第一", "最大", "最好", "唯一", "最强", "顶级", "绝对"]


def check_content_against_gt(content_items: list[dict], active_gt: dict) -> dict:
    """Verify generated content items against active Ground Truth fields.

    Returns a fact_check_report with per-item verification results.
    """
    report = {"items": [], "overall_pass": True, "issues_found": 0}
    gt_fields = set(active_gt.keys())

    for idx, item in enumerate(content_items):
        item_result = {
            "index": idx,
            "content_type": item.get("type", "unknown"),
            "gt_fields_used": [],
            "unverified_claims": [],
            "forbidden_terms": [],
            "pass": True,
        }

        text = item.get("body", "")
        if isinstance(text, dict):
            text = str(text)

        # Check for forbidden claims
        for term in FORBIDDEN_CLAIMS:
            if term in text:
                item_result["forbidden_terms"].append(term)
                item_result["pass"] = False

        # Check which GT fields are referenced
        for field in gt_fields:
            gt_value = active_gt.get(field, "")
            if isinstance(gt_value, str) and len(gt_value) > 3 and gt_value[:30] in text:
                item_result["gt_fields_used"].append(field)

        if not item_result["pass"] or item_result["forbidden_terms"]:
            report["overall_pass"] = False
            report["issues_found"] += 1

        report["items"].append(item_result)

    return report
