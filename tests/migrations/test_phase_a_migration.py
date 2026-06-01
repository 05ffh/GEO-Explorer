import pytest
from sqlalchemy import text


@pytest.mark.migration
async def test_phase_a_new_columns_exist(db_session):
    """Post-migration: verify all new columns exist."""
    cols = (await db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='collection_runs' AND column_name IN "
        "('report_quality_summary_json','template_health_report_json','report_publishable','blocking_reasons_json')"
        "ORDER BY column_name"
    ))).fetchall()
    assert len(cols) == 4

    cols_hr = (await db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='hallucination_results' AND column_name IN "
        "('claim_text','subject_type','matched_gt_field','reason','needs_human_review')"
    ))).fetchall()
    assert len(cols_hr) == 5

    cols_qt = (await db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='query_templates' AND column_name IN "
        "('template_level','question_scope')"
    ))).fetchall()
    assert len(cols_qt) == 2


@pytest.mark.migration
async def test_phase_a_indexes_exist(db_session):
    """Post-migration: verify indexes created."""
    indexes = (await db_session.execute(text(
        "SELECT indexname FROM pg_indexes WHERE tablename IN "
        "('collection_runs','query_templates','hallucination_results')"
    ))).fetchall()
    idx_names = [i[0] for i in indexes]
    assert "ix_collection_runs_report_publishable" in idx_names
    assert "ix_query_templates_question_type" in idx_names
    assert "ix_query_templates_template_level" in idx_names
    assert "ix_hallucination_results_subject_type" in idx_names
    assert "ix_hallucination_results_severity" in idx_names
