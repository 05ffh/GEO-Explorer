"""GEO Explorer — GT Review ViewModel.

Batch-loads all evidence in one query (P0-9 fix).
Computes promote readiness, field status, and progress stats.
"""
from collections import defaultdict

from sqlalchemy import select
from src.models.gt_candidate import GroundTruthCandidate
from src.models.gt_evidence import GroundTruthEvidence
from src.models.ground_truth import GroundTruthVersion
from src.schemas.ground_truth import (
    FIELD_TO_RISK_LEVEL, SOURCE_TIERS,
    HIGH_RISK_FIELD_TIER_REQUIREMENTS, FIELD_EVIDENCE_REQUIREMENTS,
)


async def build_gt_review_vm(brand, user, db) -> dict:
    """Build view model for the GT review page.

    Returns fields with pre-grouped evidence, progress stats,
    promote readiness with blocking reasons, and permissions.
    """
    # Get latest pending candidate
    candidate = (await db.execute(
        select(GroundTruthCandidate).where(
            GroundTruthCandidate.brand_id == brand.id,
            GroundTruthCandidate.status == "pending_review",
        ).order_by(GroundTruthCandidate.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    # Batch load ALL evidence for this candidate (P0-9 fix: single query, no N+1)
    evidences_by_field = defaultdict(list)
    promote_blocked = []
    if candidate:
        evidence_rows = (await db.execute(
            select(GroundTruthEvidence).where(
                GroundTruthEvidence.candidate_id == candidate.id,
            )
        )).scalars().all()
        for ev in evidence_rows:
            evidences_by_field[ev.field_name].append(ev)

        # Promote readiness: check high-risk fields have sufficient tier evidence
        for field in HIGH_RISK_FIELD_TIER_REQUIREMENTS:
            if field not in candidate.candidate_json:
                continue
            field_ev = evidences_by_field.get(field, [])
            req = HIGH_RISK_FIELD_TIER_REQUIREMENTS.get(field, "A")
            min_sources = FIELD_EVIDENCE_REQUIREMENTS.get(field, {}).get("min_sources", 1)
            req_score = SOURCE_TIERS.get(req, {}).get("score", 0.4)
            sufficient = [e for e in field_ev
                          if SOURCE_TIERS.get(e.source_tier, {}).get("score", 0) >= req_score]
            if len(field_ev) < min_sources:
                promote_blocked.append({
                    "field": field,
                    "reason": f"需要 {min_sources}+ 条证据（当前 {len(field_ev)} 条）",
                })
            elif not sufficient and req_score > 0.3:
                best = max((e.source_tier for e in field_ev), default="无")
                promote_blocked.append({
                    "field": field,
                    "reason": f"需要 {req}-级证据（当前最佳: {best}）",
                })

    # Active GT for comparison
    active_gt_result = await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand.id,
            GroundTruthVersion.status == "active",
        ).order_by(GroundTruthVersion.version.desc()).limit(1)
    )
    active_gt = active_gt_result.scalar_one_or_none()

    # Build field list with evidence
    fields = []
    if candidate:
        # Detect v2 field types from active GT for display
        field_types = {}
        if active_gt and isinstance(active_gt.ground_truth_json, dict):
            v2_fields = active_gt.ground_truth_json.get("fields", {})
            if isinstance(v2_fields, dict):
                for fn, fmeta in v2_fields.items():
                    if isinstance(fmeta, dict) and "field_type" in fmeta:
                        field_types[fn] = fmeta["field_type"]

        for fname, fval in (candidate.candidate_json or {}).items():
            risk = FIELD_TO_RISK_LEVEL.get(fname, "low")
            field_ev = evidences_by_field.get(fname, [])

            # Determine status
            if any(ev.review_status == "flagged" for ev in field_ev):
                status = "flagged"
            elif any(ev.human_confirmed for ev in field_ev):
                status = "accepted"
            else:
                status = "pending"

            # Conflict detection
            unique_values = set(ev.value for ev in field_ev if ev.value)
            has_conflict = len(unique_values) > 1

            # Best tier
            best_tier = max((ev.source_tier for ev in field_ev), default="C")

            # Infer field type from value if not in v2 schema
            ft = field_types.get(fname)
            if not ft:
                fv = str(fval)
                if fv.startswith("[") or "、" in fv:
                    ft = "list"
                elif fv.isdigit() or fv.replace(".", "").replace("%", "").isdigit():
                    ft = "number"
                else:
                    ft = "string"

            fields.append({
                "name": fname,
                "value": str(fval)[:200],
                "field_type": ft,
                "risk_level": risk,
                "status": status,
                "has_conflict": has_conflict,
                "best_tier": best_tier,
                "evidence_count": len(field_ev),
                "evidences": [{
                    "source_tier": ev.source_tier,
                    "source_name": ev.source_name,
                    "source_url": ev.source_url,
                    "excerpt": (ev.excerpt or "")[:200],
                    "value": ev.value,
                    "human_confirmed": ev.human_confirmed,
                    "review_status": ev.review_status,
                } for ev in field_ev],
            })

    # Progress stats
    total = len(fields)
    reviewed = sum(1 for f in fields if f["status"] == "accepted")
    high_risk_total = sum(1 for f in fields if f["risk_level"] == "high")
    high_risk_reviewed = sum(1 for f in fields if f["risk_level"] == "high" and f["status"] == "accepted")
    uncertain = sum(1 for f in fields if f["status"] == "flagged")
    conflicts = sum(1 for f in fields if f["has_conflict"])


    # P0-2: GT Quality summary
    quality_summary = {"total_evidence": 0, "tiers": {}, "anchors": 0, "pending_key_fields": []}
    if candidate:
        all_ev = (await db.execute(
            select(GroundTruthEvidence).where(GroundTruthEvidence.candidate_id == candidate.id)
        )).scalars().all()
        quality_summary["total_evidence"] = len(all_ev)
        for ev in all_ev:
            t = ev.source_tier or "C"
            quality_summary["tiers"][t] = quality_summary["tiers"].get(t, 0) + 1
        from src.gt.field_policy import get_high_priority_fields
        for f in get_high_priority_fields("P0"):
            if f in (candidate.candidate_json or {}):
                quality_summary["pending_key_fields"].append(f)
        quality_summary["pending_key_fields_count"] = len(quality_summary["pending_key_fields"])
        if active_gt:
            gt_json = active_gt.get_flat_json() if hasattr(active_gt, "get_flat_json") else active_gt.ground_truth_json
            for f in get_high_priority_fields("P0"):
                if gt_json.get(f"_{f}_anchor"):
                    quality_summary["anchors"] += 1


    return {
        "quality_summary": quality_summary,
        "brand": {"id": str(brand.id), "name": brand.name},
        "has_candidate": candidate is not None,
        "candidate_id": str(candidate.id) if candidate else None,
        "progress": {
            "total": total,
            "reviewed": reviewed,
            "high_risk_total": high_risk_total,
            "high_risk_reviewed": high_risk_reviewed,
            "uncertain": uncertain,
            "conflicts": conflicts,
        },
        "fields": fields,
        "active_gt": active_gt.ground_truth_json if active_gt else None,
        "can_promote": len(promote_blocked) == 0 and total > 0,
        "promote_blocked": promote_blocked,
        "permissions": {
            "can_review": user.role in ("admin", "gt_reviewer"),
            "can_promote": user.role in ("admin", "gt_reviewer"),
        },
    }
