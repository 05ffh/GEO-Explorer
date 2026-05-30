# GEO Explorer — ViewModel Layer
# Pre-computes all display values so templates only render.
# No business logic in Jinja2 templates.

from src.view_models.dashboard import build_dashboard_vm, get_latest_completed_run
from src.view_models.gt_review import build_gt_review_vm
from src.view_models.evidence import build_evidence_vm
from src.view_models.hallucination import build_hallucination_vm, cluster_key
from src.view_models.action import build_action_vm, can_transition, TRANSITION_GUARDS
from src.view_models.content import build_content_vm
from src.view_models.trends import build_trends_vm, compute_attribution, get_kpi_value, get_kpi_threshold, infer_target_kpi

__all__ = [
    "build_dashboard_vm",
    "get_latest_completed_run",
    "build_gt_review_vm",
    "build_evidence_vm",
    "build_hallucination_vm",
    "cluster_key",
    "build_action_vm",
    "can_transition",
    "TRANSITION_GUARDS",
    "build_content_vm",
    "build_trends_vm",
    "compute_attribution_label",
]
