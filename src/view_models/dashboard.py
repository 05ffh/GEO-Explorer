# GEO Explorer — Dashboard ViewModel
# Pre-computes all display values for the brand overview page.
# Templates only render — no business logic in Jinja2.

from sqlalchemy import select, desc, func
from src.models.collection_run import CollectionRun
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.ground_truth import GroundTruthVersion
from src.models.gt_candidate import GroundTruthCandidate
from src.models.hallucination import HallucinationResult
from src.models.action_theme import ActionTheme
from src.models.content_package import ContentPackage
from src.schemas.ground_truth import KPI_DISPLAY_NAMES


KPI_KEYS = [
    "sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate",
    "scenario_recall", "semantic_stability", "differentiation",
    "cross_platform_consistency", "recommendation_quality",
]


async def get_latest_completed_run(brand_id, db):
    """Get the most recent collection run with completed analysis."""
    result = await db.execute(
        select(CollectionRun).where(
            CollectionRun.brand_id == brand_id,
            CollectionRun.analysis_status == "completed",
        ).order_by(desc(CollectionRun.analysis_completed_at)).limit(1)
    )
    return result.scalar_one_or_none()


async def build_dashboard_vm(brand, user, db) -> dict:
    """Build view model for the brand overview dashboard page."""
    return {}
