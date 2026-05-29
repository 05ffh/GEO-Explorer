# GEO Explorer — AI Evidence ViewModel
from sqlalchemy import select, desc
from src.models.query_result import QueryResult
from src.models.hallucination import HallucinationResult


async def build_evidence_vm(brand, filters, user, db) -> dict:
    """Build view model for the AI evidence page."""
    return {}
