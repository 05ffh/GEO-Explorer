"""P2-4: Review Feedback Service — claim, review, feedback generation, calibration export."""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func

from src.models.hallucination import HallucinationResult
from src.models.hallucination_review_log import HallucinationReviewLog
from src.models.review_feedback import GTUpdateCandidate, ReviewFeedbackItem
from src.models.user import User

logger = logging.getLogger(__name__)

CLAIM_TIMEOUT_HOURS = 2

VALID_REVIEW_STATUSES = {"pending", "claimed", "completed", "skipped", "reopened", "expired"}
VALID_REVIEW_DECISIONS = {
    "confirm_auto_correct", "mark_false_positive", "mark_false_negative",
    "correct_verdict", "gt_needs_update", "template_needs_fix",
    "detector_needs_calibration", "inconclusive", "skip",
}
VALID_REVIEW_PRIORITIES = {"high", "medium", "low"}


class ReviewService:
    """Human review workflow: claim, complete, skip, reopen, batch."""

    async def _get_or_404(self, db: AsyncSession, result_id: str) -> HallucinationResult:
        r = (await db.execute(
            select(HallucinationResult).where(HallucinationResult.id == result_id)
        )).scalar_one_or_none()
        if not r:
            raise ValueError("HallucinationResult not found")
        return r

    def _snapshot(self, r: HallucinationResult) -> dict:
        return {
            "verdict": r.verdict, "severity": r.severity,
            "claim_type": r.claim_type, "field_name": r.field_name,
            "review_status": r.review_status, "review_decision": r.review_decision,
            "evidence_strength": (
                r.evidence_consensus_json.get("evidence_strength_level", "")
                if r.evidence_consensus_json else ""
            ),
        }

    def _write_log(
        self, r: HallucinationResult, action: str, reviewer_id,
        old_status: str, new_status: str, notes: str = "",
        decision: str = "", corrected_value: str = "",
        before: dict | None = None, after: dict | None = None,
    ) -> HallucinationReviewLog:
        return HallucinationReviewLog(
            organization_id=getattr(r, "organization_id", None),
            hallucination_result_id=r.id,
            collection_run_id=r.collection_run_id,
            query_result_id=r.query_result_id,
            reviewer_id=reviewer_id,
            action=action,
            old_review_status=old_status,
            new_review_status=new_status,
            old_verdict=before.get("verdict", "") if before else r.verdict,
            new_verdict=after.get("verdict", "") if after else r.verdict,
            old_severity=before.get("severity", "") if before else r.severity,
            new_severity=after.get("severity", "") if after else r.severity,
            old_claim_nature=before.get("claim_type", "") if before else r.claim_type,
            new_claim_nature=after.get("claim_type", "") if after else r.claim_type,
            old_evidence_strength=before.get("evidence_strength", "") if before else "",
            new_evidence_strength=after.get("evidence_strength", "") if after else "",
            review_decision=decision,
            notes=notes,
            corrected_value=corrected_value,
            snapshot_before_json=before,
            snapshot_after_json=after,
        )

    # ── Claim ──────────────────────────────────────────────────────────

    async def claim(self, db: AsyncSession, result_id: str, user: User) -> dict:
        r = await self._get_or_404(db, result_id)
        if r.review_status not in ("pending", "reopened"):
            raise ValueError(f"无法认领状态为 {r.review_status} 的审核项")
        before = self._snapshot(r)
        old_status = r.review_status
        r.review_status = "claimed"
        r.claimed_by = user.id
        r.claimed_at = datetime.now(timezone.utc)
        r.claim_expires_at = datetime.now(timezone.utc) + timedelta(hours=CLAIM_TIMEOUT_HOURS)
        log = self._write_log(r, "claimed", user.id, old_status, "claimed", before=before)
        db.add(log)
        await db.flush()
        return {"status": "claimed", "claimed_by": str(user.id), "expires_at": r.claim_expires_at.isoformat()}

    # ── Complete review ────────────────────────────────────────────────

    async def complete_review(
        self, db: AsyncSession, result_id: str, user: User,
        decision: str, notes: str = "", verdict: str = "",
        severity: str = "", corrected_value: str = "",
    ) -> dict:
        r = await self._get_or_404(db, result_id)
        if r.review_status != "claimed":
            raise ValueError(f"状态 {r.review_status} 不可提交审核")
        if r.claimed_by and str(r.claimed_by) != str(user.id):
            raise ValueError("只有认领人可提交审核")
        if decision not in VALID_REVIEW_DECISIONS and decision != "skip":
            raise ValueError(f"无效的 review_decision: {decision}")

        before = self._snapshot(r)
        old_status = r.review_status
        r.review_status = "completed"
        r.review_decision = decision
        r.review_notes = notes
        r.human_reviewed = True
        r.reviewer_id = user.id
        r.reviewed_at = datetime.now(timezone.utc)
        if verdict:
            r.human_verdict = verdict
        if severity:
            r.severity = severity
        if corrected_value:
            r.corrected_value = corrected_value
        if decision == "inconclusive":
            r.needs_human_review = True  # stay flagged
        r.claim_expires_at = None
        after = self._snapshot(r)

        log = self._write_log(r, "completed", user.id, old_status, "completed",
                              notes=notes, decision=decision, corrected_value=corrected_value,
                              before=before, after=after)
        db.add(log)

        # Generate feedback if applicable
        if decision == "gt_needs_update" and corrected_value:
            await self._create_gt_candidate(db, r, user, corrected_value)
        if decision in ("mark_false_positive", "mark_false_negative", "detector_needs_calibration"):
            await self._create_calibration_feedback(db, r, user, decision)

        await db.flush()
        return {"status": "completed", "decision": decision}

    # ── Skip ───────────────────────────────────────────────────────────

    async def skip_review(self, db: AsyncSession, result_id: str, user: User, reason: str) -> dict:
        r = await self._get_or_404(db, result_id)
        before = self._snapshot(r)
        old_status = r.review_status
        r.review_status = "skipped"
        r.review_decision = "skip"
        r.review_notes = reason
        log = self._write_log(r, "skipped", user.id, old_status, "skipped",
                              notes=reason, decision="skip", before=before)
        db.add(log)
        await db.flush()
        return {"status": "skipped", "reason": reason}

    # ── Reopen ─────────────────────────────────────────────────────────

    async def reopen(self, db: AsyncSession, result_id: str, user: User) -> dict:
        r = await self._get_or_404(db, result_id)
        if r.review_status not in ("completed", "skipped"):
            raise ValueError(f"状态 {r.review_status} 不可 reopen")
        before = self._snapshot(r)
        old_status = r.review_status
        r.review_status = "reopened"
        r.claimed_by = None
        r.claimed_at = None
        r.claim_expires_at = None
        log = self._write_log(r, "reopened", user.id, old_status, "reopened", before=before)
        db.add(log)
        await db.flush()
        return {"status": "reopened"}

    # ── Release (timeout / admin release) ──────────────────────────────

    async def release_claim(self, db: AsyncSession, result_id: str) -> dict:
        r = await self._get_or_404(db, result_id)
        if r.review_status != "claimed":
            raise ValueError("只能释放 claimed 项")
        before = self._snapshot(r)
        r.review_status = "pending"
        r.claimed_by = None
        r.claimed_at = None
        r.claim_expires_at = None
        log = self._write_log(r, "released", None, "claimed", "pending", before=before)
        db.add(log)
        await db.flush()
        return {"status": "pending"}

    # ── Batch dry-run ──────────────────────────────────────────────────

    async def batch_dry_run(self, db: AsyncSession, result_ids: list[str]) -> dict:
        import uuid as _uuid
        from datetime import datetime, timezone
        affected = 0
        blocked = []
        sev_count = {}
        allowed_ids = []
        for rid in result_ids:
            try:
                r = await self._get_or_404(db, rid)
                if r.review_status not in ("pending", "reopened"):
                    blocked.append({"id": rid, "reason": f"状态 {r.review_status} 不可批量操作"})
                    continue
                if r.severity in ("P0", "P1"):
                    blocked.append({"id": rid, "reason": f"{r.severity} 需要单独审核"})
                    continue
                affected += 1
                sev_count[r.severity] = sev_count.get(r.severity, 0) + 1
                allowed_ids.append(rid)
            except Exception:
                blocked.append({"id": rid, "reason": "不存在"})
        token = str(_uuid.uuid4())
        # Store token → allowed_ids mapping in memory (TTL 5 min)
        if not hasattr(self, '_dry_run_tokens'):
            self._dry_run_tokens = {}
        self._dry_run_tokens[token] = {
            "allowed_ids": allowed_ids, "action": "skip",
            "created_at": datetime.now(timezone.utc),
        }
        return {
            "dry_run_token": token,
            "affected_count": affected, "severity_breakdown": sev_count,
            "blocked_items": blocked,
        }

    # ── Batch skip ─────────────────────────────────────────────────────

    async def batch_skip(self, db: AsyncSession, result_ids: list[str], user: User,
                         reason: str, dry_run_token: str = "",
                         idempotency_key: str = "") -> dict:
        # Validate dry_run_token
        if dry_run_token and hasattr(self, '_dry_run_tokens'):
            token_data = self._dry_run_tokens.get(dry_run_token)
            if not token_data:
                raise ValueError("dry_run_token 无效或已过期，请重新预览")
            if token_data["action"] != "skip":
                raise ValueError("dry_run_token action 不匹配")
            # Clean up token
            del self._dry_run_tokens[dry_run_token]

        # Idempotency check
        if idempotency_key and hasattr(self, '_batch_idem_keys'):
            if idempotency_key in self._batch_idem_keys:
                return {"skipped": 0, "idempotent": True, "message": "已处理过，跳过"}
        if not hasattr(self, '_batch_idem_keys'):
            self._batch_idem_keys = set()

        dry = await self.batch_dry_run(db, result_ids)
        if dry["blocked_items"]:
            raise ValueError(f"存在 {len(dry['blocked_items'])} 项阻塞，请先执行 dry-run")
        skipped = 0
        for rid in result_ids:
            try:
                await self.skip_review(db, rid, user, reason)
                skipped += 1
            except Exception:
                pass
        if idempotency_key:
            self._batch_idem_keys.add(idempotency_key)
        return {"skipped": skipped, "idempotent": False}

    # ── Feedback generation ───────────────────────────────────────────

    async def _create_gt_candidate(self, db: AsyncSession, r: HallucinationResult,
                                    user: User, corrected_value: str):
        c = GTUpdateCandidate(
            organization_id=getattr(r, "organization_id", None),
            brand_id=r.brand_id,
            field_name=r.field_name,
            current_gt_value=r.ground_truth_value,
            proposed_value=corrected_value,
            corrected_value=corrected_value,
            source_hallucination_result_id=r.id,
            created_by=user.id,
            status="pending",
        )
        db.add(c)

    async def _create_calibration_feedback(self, db: AsyncSession, r: HallucinationResult,
                                            user: User, decision: str):
        item = ReviewFeedbackItem(
            organization_id=getattr(r, "organization_id", None),
            feedback_type="detector_calibration",
            source_hallucination_result_ids=[str(r.id)],
            brand_id=r.brand_id,
            field_name=r.field_name,
            question_type=getattr(r, "predicate_type", ""),
            summary=f"{decision}: {r.ai_claim[:100]}",
            recommendation=f"校准样本: auto={r.verdict} human_decision={decision}",
            status="pending",
            priority=r.severity == "P0" and "high" or "medium",
        )
        db.add(item)

    # ── Get review queue ───────────────────────────────────────────────

    async def get_review_queue(
        self, db: AsyncSession, org_id=None, status="pending",
        priority=None, severity=None, page=1, page_size=20,
    ) -> dict:
        q = select(HallucinationResult).where(
            HallucinationResult.needs_human_review == True,
            HallucinationResult.review_status == status,
        )
        if priority:
            q = q.where(HallucinationResult.review_priority == priority)
        if severity:
            q = q.where(HallucinationResult.severity == severity)
        q = q.order_by(
            HallucinationResult.review_priority == "high",
            HallucinationResult.severity == "P0",
        ).offset((page-1)*page_size).limit(page_size)
        rows = (await db.execute(q)).scalars().all()
        items = []
        for r in rows:
            items.append({
                "id": str(r.id), "field_name": r.field_name,
                "ai_claim": r.ai_claim[:150], "verdict": r.verdict,
                "severity": r.severity, "claim_type": r.claim_type,
                "review_status": r.review_status, "review_priority": r.review_priority,
                "review_reason": r.review_reason, "ground_truth_value": r.ground_truth_value,
                "claimed_by": str(r.claimed_by) if r.claimed_by else None,
                "evidence_strength": (
                    r.evidence_consensus_json.get("evidence_strength_level", "")
                    if r.evidence_consensus_json else ""
                ),
            })
        return {"items": items, "page": page, "page_size": page_size}

    # ── Calibration export ─────────────────────────────────────────────

    async def export_calibration_samples(self, db: AsyncSession, org_id=None, limit=100) -> list[dict]:
        q = select(HallucinationResult).where(
            HallucinationResult.human_reviewed == True,
            HallucinationResult.review_decision.in_(
                ("mark_false_positive", "mark_false_negative", "correct_verdict")),
        ).order_by(HallucinationResult.reviewed_at.desc()).limit(limit)
        rows = (await db.execute(q)).scalars().all()
        samples = []
        for r in rows:
            samples.append({
                "sample_id": str(r.id),
                "claim_text": r.ai_claim,
                "auto_verdict": r.verdict,
                "human_verdict": r.human_verdict,
                "review_decision": r.review_decision,
                "predicate_type": r.predicate_type if hasattr(r, "predicate_type") else "",
                "claim_nature": r.claim_type,
                "evidence_strength": (
                    r.evidence_consensus_json.get("evidence_strength_level", "")
                    if r.evidence_consensus_json else ""
                ),
                "reason": r.reason[:200],
            })
        return samples


review_service = ReviewService()
