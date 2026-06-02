"""Metric-template mapping loader, validator, and KPI eligibility helpers."""
import yaml
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.query_result import QueryResult

_MAPPING = None


def load_metric_mapping() -> dict:
    global _MAPPING
    if _MAPPING is None:
        path = Path(__file__).parent.parent.parent / "config" / "metric_template_mapping.yaml"
        with open(path) as f:
            _MAPPING = yaml.safe_load(f)
    return _MAPPING


def validate_metric_mapping(mapping: dict) -> list[str]:
    """Validate mapping config. Returns list of error strings."""
    from src.analyzer.enums import QuestionType
    errors = []
    known_kpis = {
        "sov", "first_rec_rate", "brand_mention_rate", "information_accuracy",
        "completeness_rate", "citation_rate", "competitor_accuracy",
        "scenario_coverage", "trust_risk_rate", "hallucination_rate",
    }
    known_qtypes = {e.value for e in QuestionType}
    core_kpis = {"information_accuracy", "completeness_rate", "citation_rate",
                 "hallucination_rate", "brand_mention_rate"}

    for kpi_key, cfg in mapping.items():
        if kpi_key in ("schema_version", "mapping_version"):
            continue
        if kpi_key not in known_kpis:
            errors.append(f"Unknown KPI key: {kpi_key}")
        for qt in cfg.get("allowed", []):
            if qt not in known_qtypes:
                errors.append(f"{kpi_key}.allowed: unknown question_type '{qt}'")
        for qt, cond in cfg.get("conditional", {}).items():
            if qt not in known_qtypes:
                errors.append(f"{kpi_key}.conditional: unknown question_type '{qt}'")
            if cond != "target_brand_claim_only":
                errors.append(f"{kpi_key}.conditional[{qt}]: unknown condition '{cond}'")
        for qt in cfg.get("excluded", []):
            if qt not in known_qtypes:
                errors.append(f"{kpi_key}.excluded: unknown question_type '{qt}'")
        if kpi_key in core_kpis and "generic_advice" not in cfg.get("excluded", []):
            errors.append(f"{kpi_key}: generic_advice must be excluded")
        all_q = set(cfg.get("allowed", [])) | set(cfg.get("conditional", {}).keys()) | set(cfg.get("excluded", []))
        expected = len(cfg.get("allowed", [])) + len(cfg.get("conditional", {})) + len(cfg.get("excluded", []))
        if len(all_q) != expected:
            errors.append(f"{kpi_key}: duplicate question_type across allowed/conditional/excluded")

    for kpi in known_kpis:
        if kpi not in mapping:
            errors.append(f"Missing KPI: {kpi}")
    return errors


def is_query_eligible_for_kpi(template, kpi_key: str) -> tuple[bool, str | None]:
    """Returns (eligible, condition)."""
    mapping = load_metric_mapping().get(kpi_key, {})
    qt = getattr(template, 'question_type', 'brand_definition')
    if qt in mapping.get("excluded", []):
        return False, f"excluded question_type: {qt}"
    if qt in mapping.get("allowed", []):
        return True, None
    if qt in mapping.get("conditional", {}):
        return True, mapping["conditional"][qt]
    return False, f"unmapped question_type: {qt}"


async def get_kpi_eligible_results(
    kpi_key: str, brand_id: str, collection_run_id: str | None, db: AsyncSession,
) -> list[QueryResult]:
    """Return QueryResults from templates eligible for the given KPI.

    Only results whose template question_type is in allowed or conditional
    (not excluded) for this KPI are returned.
    """
    mapping = load_metric_mapping().get(kpi_key, {})
    if not mapping:
        return []
    eligible_qtypes = set(mapping.get("allowed", [])) | set(mapping.get("conditional", {}).keys())
    if not eligible_qtypes:
        return []
    from src.models.query_template import QueryTemplate as QT
    q = select(QueryResult).join(QT, QueryResult.template_id == QT.id).where(
        QueryResult.brand_id == brand_id,
        QueryResult.status == "success",
        QT.question_type.in_(eligible_qtypes),
        QT.is_active == True,  # noqa: E712
    )
    if collection_run_id:
        q = q.where(QueryResult.collection_run_id == collection_run_id)
    return list((await db.execute(q)).scalars().all())
