"""Phase 10 end-to-end verification: GT collect → review → promote → KPI integration."""

import pytest


@pytest.mark.asyncio
async def test_gt_pipeline_e2e(db_session, monkeypatch):
    """Full GT pipeline: trigger collect → review → promote → verify active GT."""
    from src.models.organization import Organization
    from src.models.brand import Brand
    from src.models.user import User

    org = Organization(name="E2EOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="E2EBrand", industry="Technology")
    db_session.add(brand)
    user = User(organization_id=org.id, email="e2e@test.com", name="E2E", role="admin", password_hash="hash")
    db_session.add(user)
    await db_session.commit()

    from src.collector import gt_collector as gc

    async def mock_collect_from_ai(*a, **kw):
        return []

    async def mock_collect_from_search(*a, **kw):
        return []

    monkeypatch.setattr(gc, "_collect_from_ai_platforms", mock_collect_from_ai)
    monkeypatch.setattr(gc, "_collect_from_search", mock_collect_from_search)

    # 1. Trigger GT collection
    candidate = await gc.collect_gt_candidate(str(brand.id), str(org.id), db_session)
    assert candidate is not None
    assert candidate.status == "pending_review"

    # 2. Review candidate: accept all and populate required fields
    candidate.candidate_json = {
        "official_name": "E2EBrand",
        "aliases": ["E2E"],
        "industry": "Technology",
        "category": "SaaS",
        "positioning": "E2E Platform",
        "core_products": "Product X",
        "target_users": "Enterprises",
        "core_scenarios": "Testing",
        "key_differentiators": "Speed",
        "official_domains": "e2e.com",
        "source_of_truth_by_field": {},
    }
    await db_session.commit()

    # 3. Simulate promote (manual check)
    from src.api.ground_truth import _check_required_fields, _check_high_risk_completion, _compute_coverage
    completeness = _check_required_fields(candidate)
    assert completeness["complete"], f"Missing: {completeness['missing']}"
    assert _check_high_risk_completion(candidate)
    assert _compute_coverage(candidate) > 0.9


@pytest.mark.asyncio
async def test_content_package_pipeline_e2e(db_session):
    """Content package pipeline: GT → fact-check → schema → package."""
    from src.models.organization import Organization
    from src.models.brand import Brand
    from src.models.ground_truth import GroundTruthVersion
    from src.models.action_plan import ActionPlan
    from src.models.user import User

    org = Organization(name="E2EContent")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="ContentBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()

    # Active GT
    gt = GroundTruthVersion(
        brand_id=brand.id,
        version=1,
        ground_truth_json={"official_name": "ContentBrand", "positioning": "Content platform"},
        status="active",
        required_fields_complete=True,
        user_confirmed=True,
    )
    db_session.add(gt)
    await db_session.commit()

    # Action plan
    plan = ActionPlan(
        brand_id=brand.id,
        organization_id=org.id,
        trigger_type="test",
        action_type="test",
        suggested_content_type="FAQ",
    )
    db_session.add(plan)
    await db_session.commit()

    # Generate content package
    from src.actions.content_package import build_content_package
    content_items = [{"type": "FAQ", "title": "FAQ", "body": "ContentBrand is a content platform for testing."}]
    schema_items = [{"@type": "FAQPage"}]
    fact_check = {"overall_pass": True, "issues_found": 0}

    pkg = await build_content_package(
        str(plan.id), str(brand.id), str(org.id),
        content_items, schema_items, fact_check, db_session,
    )
    assert pkg.status == "draft"
    assert len(pkg.content_items) == 1

    # Export
    from src.actions.content_package import export_content_package
    exported = export_content_package(pkg)
    assert "markdown" in exported
    assert "json_ld" in exported
    assert "checklist" in exported


@pytest.mark.asyncio
async def test_extended_kpis_flow(db_session):
    """Verify all 10 KPIs (5 original + 5 new) can be computed."""
    from src.models.organization import Organization
    from src.models.brand import Brand
    from src.models.collection_run import CollectionRun
    from src.models.query_template import QueryTemplate
    from src.models.query_result import QueryResult
    from datetime import datetime, timezone

    org = Organization(name="KPIOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="KPIBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()
    run = CollectionRun(brand_id=brand.id, organization_id=org.id, trigger_type="manual",
                        collection_status="completed", analysis_status="not_started")
    db_session.add(run)
    await db_session.commit()
    tmpl = QueryTemplate(organization_id=org.id, dimension="test", template_text="Test question template")
    db_session.add(tmpl)
    await db_session.commit()

    for i in range(10):
        qr = QueryResult(
            collection_run_id=run.id, brand_id=brand.id, organization_id=org.id,
            template_id=tmpl.id,
            platform="deepseek" if i % 3 == 0 else "kimi" if i % 3 == 1 else "doubao",
            question=f"Query {i} about KPIBrand",
            answer_text=f"KPIBrand is an innovative tech platform with unique capabilities. Answer {i}.",
            status="success",
            collected_at=datetime.now(timezone.utc),
        )
        db_session.add(qr)
    await db_session.commit()

    from src.analyzer import sov, first_rec, accuracy, completeness, citation
    from src.analyzer import scenario_recall, semantic_stability, differentiation
    from src.analyzer import cross_platform_consistency, recommendation_quality

    kpi_functions = [
        sov.compute_sov,
        first_rec.compute_first_rec,
        accuracy.compute_accuracy,
        completeness.compute_completeness,
        citation.compute_citation_rate,
        scenario_recall.compute_scenario_recall,
        semantic_stability.compute_semantic_stability,
        differentiation.compute_differentiation,
        cross_platform_consistency.compute_cross_platform_consistency,
        recommendation_quality.compute_recommendation_quality,
    ]
    for kpi_fn in kpi_functions:
        result = await kpi_fn(str(brand.id), str(run.id), db_session)
        assert isinstance(result, dict)
        # Each KPI returns a dict with at least one numeric metric
        numeric_keys = ["value", "sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate"]
        has_metric = any(k in result for k in numeric_keys)
        assert has_metric, f"{kpi_fn.__name__} returned: {result}"
