import pytest


@pytest.mark.asyncio
async def test_scenario_recall_empty(db_session):
    """Scenario recall returns zero when no query results."""
    from src.analyzer.scenario_recall import compute_scenario_recall
    result = await compute_scenario_recall(
        "00000000-0000-0000-0000-000000000000", None, db_session,
    )
    assert result["value"] == 0.0
    assert result["sample_size"] == 0
    assert result["confidence"] == "low"


@pytest.mark.asyncio
async def test_semantic_stability_empty(db_session):
    """Semantic stability returns zero when no query results."""
    from src.analyzer.semantic_stability import compute_semantic_stability
    result = await compute_semantic_stability(
        "00000000-0000-0000-0000-000000000000", None, db_session,
    )
    assert result["value"] == 0.0
    assert result["sample_size"] == 0


@pytest.mark.asyncio
async def test_differentiation_empty(db_session):
    """Differentiation returns zero when no query results."""
    from src.analyzer.differentiation import compute_differentiation
    result = await compute_differentiation(
        "00000000-0000-0000-0000-000000000000", None, db_session,
    )
    assert result["value"] == 0.0
    assert result["confidence"] == "low"


@pytest.mark.asyncio
async def test_cross_platform_consistency_empty(db_session):
    """Cross-platform consistency returns zero with no data."""
    from src.analyzer.cross_platform_consistency import compute_cross_platform_consistency
    result = await compute_cross_platform_consistency(
        "00000000-0000-0000-0000-000000000000", None, db_session,
    )
    assert result["value"] == 0.0
    assert result["sample_size"] == 0


@pytest.mark.asyncio
async def test_recommendation_quality_empty(db_session):
    """Recommendation quality returns zero with no data."""
    from src.analyzer.recommendation_quality import compute_recommendation_quality
    result = await compute_recommendation_quality(
        "00000000-0000-0000-0000-000000000000", None, db_session,
    )
    assert result["value"] == 0.0
    assert result["sample_size"] == 0


@pytest.mark.asyncio
async def test_all_extended_kpis_return_consistent_structure(db_session, monkeypatch):
    """All 5 extended KPIs return {value, numerator, denominator, sample_size, confidence}."""
    from src.models.organization import Organization
    from src.models.brand import Brand
    from src.models.collection_run import CollectionRun
    from src.models.query_template import QueryTemplate
    from src.models.query_result import QueryResult
    from datetime import datetime, timezone

    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()
    run = CollectionRun(brand_id=brand.id, organization_id=org.id, trigger_type="gt")
    db_session.add(run)
    await db_session.commit()
    tmpl = QueryTemplate(
        organization_id=org.id,
        dimension="test",
        template_text="Test question template",
        is_active=True,
    )
    db_session.add(tmpl)
    await db_session.commit()

    for i in range(6):
        qr = QueryResult(
            collection_run_id=run.id,
            brand_id=brand.id,
            organization_id=org.id,
            template_id=tmpl.id,
            platform="deepseek" if i % 2 == 0 else "kimi",
            question=f"Question {i}",
            answer_text=f"TestBrand is a great company with unique features. Sample answer {i}.",
            status="success",
            collected_at=datetime.now(timezone.utc),
        )
        db_session.add(qr)
    await db_session.commit()

    from src.analyzer.scenario_recall import compute_scenario_recall
    from src.analyzer.semantic_stability import compute_semantic_stability
    from src.analyzer.differentiation import compute_differentiation
    from src.analyzer.cross_platform_consistency import compute_cross_platform_consistency
    from src.analyzer.recommendation_quality import compute_recommendation_quality

    kpis = [
        compute_scenario_recall(brand.id, run.id, db_session),
        compute_semantic_stability(brand.id, run.id, db_session),
        compute_differentiation(brand.id, run.id, db_session),
        compute_cross_platform_consistency(brand.id, run.id, db_session),
        compute_recommendation_quality(brand.id, run.id, db_session),
    ]
    results = [await k for k in kpis]
    for r in results:
        assert "value" in r
        assert "numerator" in r
        assert "denominator" in r
        assert "sample_size" in r
        assert "confidence" in r
        assert r["sample_size"] > 0
        assert r["confidence"] in ("high", "medium", "low")
