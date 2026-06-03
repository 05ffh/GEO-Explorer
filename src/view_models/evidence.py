"""P2-FRONTEND: AI Evidence viewer VM — claim verification chain + source traceability."""
from sqlalchemy import select, desc
from src.models.hallucination import HallucinationResult
from src.models.query_result import QueryResult


async def build_evidence_vm(brand, filters, user, db) -> dict:
    # Get hallucinations with evidence_consensus_json and ground truth data
    q = select(HallucinationResult).where(
        HallucinationResult.brand_id == brand.id,
    ).order_by(desc(HallucinationResult.created_at)).limit(60)
    rows = (await db.execute(q)).scalars().all()

    items = []
    for h in rows:
        evidence = h.evidence_consensus_json or {}
        items.append({
            "id": str(h.id),
            "field_name": h.field_name,
            "ai_claim": h.ai_claim or "",
            "claim_text": h.claim_text or "",
            "verdict": h.verdict,
            "severity": h.severity,
            "error_type": h.error_type or "",
            "claim_type": h.claim_type,
            "subject_type": h.subject_type,
            "ground_truth_value": h.ground_truth_value or "",
            "reason": h.reason or "",
            "human_reviewed": h.human_reviewed,
            "human_verdict": h.human_verdict or "",
            "needs_human_review": h.needs_human_review,
            # Evidence chain
            "evidence_strength": evidence.get("evidence_strength_level", ""),
            "agreement_ratio": evidence.get("agreement_ratio", 0),
            "best_tier": evidence.get("best_tier", ""),
            "best_source": evidence.get("best_source", {}),
            "conflict_level": evidence.get("conflict_level", "none"),
            "has_conflict": evidence.get("has_conflict", False),
            "total_sources": evidence.get("total_sources", 0),
            "consensus_value": evidence.get("consensus_value", ""),
            # Debug evidence from reason field
            "has_llm_judge": "llm_verdict" in (h.reason or "").lower() or "llm" in (h.reason or "").lower(),
            # Review
            "review_status": h.review_status if hasattr(h, "review_status") else "",
            "review_decision": h.review_decision if hasattr(h, "review_decision") else "",
        })

    # KPI-bound evidence summary
    severity_counts = {}
    verdict_counts = {}
    strength_counts = {}
    for item in items:
        sev = item["severity"]
        severity_counts[sev] = severity_counts.get(sev, 0) + 1
        ver = item["verdict"]
        verdict_counts[ver] = verdict_counts.get(ver, 0) + 1
        st = item["evidence_strength"] or "unknown"
        strength_counts[st] = strength_counts.get(st, 0) + 1

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "items": items,
        "summary": {
            "total": len(items),
            "by_severity": severity_counts,
            "by_verdict": verdict_counts,
            "by_evidence_strength": strength_counts,
            "needs_review": sum(1 for i in items if i["needs_human_review"]),
            "reviewed_count": sum(1 for i in items if i["human_reviewed"]),
        },
        "permissions": {
            "can_review": user.role in ("admin","analyst","gt_reviewer","hallucination_reviewer","senior_reviewer"),
        },
    }
