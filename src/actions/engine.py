import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.hallucination import HallucinationResult
from src.models.action_plan import ActionPlan, VALID_TRANSITIONS
from src.analyzer.enums import HallucinationVerdict

TRIGGER_MAP = {
    "P0": {"action_type": "definition_correction", "content_type": "FAQ"},
    "P1": {"action_type": "authority_building", "content_type": "Q&A"},
    "P2": {"action_type": "content_enrichment", "content_type": "Tutorial"},
}


def validate_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, [])


async def generate_action_plans(
    brand_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession,
) -> list[ActionPlan]:
    hallucinations = (await db.execute(
        select(HallucinationResult).where(
            HallucinationResult.brand_id == brand_id,
            HallucinationResult.human_reviewed == True,  # noqa: E712
            HallucinationResult.verdict == HallucinationVerdict.CONTRADICTED,
        )
    )).scalars().all()

    plans = []
    for h in hallucinations:
        trigger = TRIGGER_MAP.get(h.field_level, TRIGGER_MAP["P2"])
        plan = ActionPlan(
            brand_id=brand_id,
            organization_id=org_id,
            trigger_type=f"field_{h.field_name}_error",
            action_type=trigger["action_type"],
            priority=h.field_level,
            evidence_hallucination_ids=[h.id],
            ai_wrong_claims={"claim": h.ai_claim},
            correct_ground_truth={
                "field": h.field_name, "value": h.ground_truth_value,
            },
            suggested_content_type=trigger["content_type"],
            acceptance_criteria=(
                f"Field '{h.field_name}' hallucination resolved: "
                f"AI should state '{h.ground_truth_value[:100]}'"
            ),
            status="pending",
        )
        db.add(plan)
        plans.append(plan)

    await db.commit()
    return plans


async def update_action_status(
    action_id: uuid.UUID, new_status: str, db: AsyncSession,
) -> ActionPlan:
    action = (await db.execute(
        select(ActionPlan).where(ActionPlan.id == action_id)
    )).scalar_one()
    if not validate_transition(action.status, new_status):
        raise ValueError(f"Invalid transition: {action.status} -> {new_status}")
    action.status = new_status
    await db.commit()
    return action
