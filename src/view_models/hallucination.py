# GEO Explorer — Hallucination Risk ViewModel
from sqlalchemy import select
from src.models.hallucination import HallucinationResult


def cluster_key(h: HallucinationResult, dimension: str = "") -> tuple:
    """P0-10 fix: cluster by (error_type, severity, field_name, dimension)."""
    return (h.error_type or "unknown", h.severity, h.field_name, dimension or "")


async def build_hallucination_vm(brand, filters, user, db) -> dict:
    """Build view model for the hallucination risk page."""
    return {}
