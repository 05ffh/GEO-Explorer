# GEO Explorer — GT Review ViewModel
from collections import defaultdict
from sqlalchemy import select
from src.models.gt_candidate import GroundTruthCandidate
from src.models.gt_evidence import GroundTruthEvidence
from src.models.ground_truth import GroundTruthVersion
from src.schemas.ground_truth import FIELD_TO_RISK_LEVEL, SOURCE_TIERS, HIGH_RISK_FIELD_TIER_REQUIREMENTS


async def build_gt_review_vm(brand, user, db) -> dict:
    """Build view model for the GT review page."""
    return {}
