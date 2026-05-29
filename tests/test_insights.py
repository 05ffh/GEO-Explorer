import pytest
from datetime import datetime
from src.analyzer.insights import generate_insights
from src.models.organization import Organization
from src.models.brand import Brand
from src.models.collection_run import CollectionRun
from src.models.query_result import QueryResult
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.hallucination import HallucinationResult
from src.models.query_template import QueryTemplate


async def _seed_insight_data(db_session, platforms, field_name="industry", severity="P0"):
    """Helper: seed org+brand+run+metrics+query_results+hallucinations."""
    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()

    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.flush()

    n = len(platforms)
    run = CollectionRun(
        organization_id=org.id, brand_id=brand.id,
        collection_status="completed", analysis_status="completed",
        total_queries=n, success_count=n, failure_count=0,
    )
    db_session.add(run)
    await db_session.flush()

    tmpl = QueryTemplate(dimension="定义认知", template_text="{品牌} 是什么？", priority=1, is_active=True)
    db_session.add(tmpl)
    await db_session.flush()

    snap = MetricsSnapshot(
        brand_id=brand.id, organization_id=org.id,
        collection_run_id=run.id, week_start=datetime.utcnow().date(),
        sov=0.78, first_rec_rate=0.65, accuracy_rate=0.82,
        completeness_rate=0.71, citation_rate=0.43, sample_size=n,
        details={"citation": {"by_platform": {
            "deepseek": {"citation_rate": 0.31},
            "kimi": {"citation_rate": 0.67},
            "doubao": {"citation_rate": 0.45},
        }}},
    )
    db_session.add(snap)
    await db_session.flush()

    for p in platforms:
        qr = QueryResult(
            brand_id=brand.id, organization_id=org.id,
            collection_run_id=run.id, platform=p,
            template_id=tmpl.id, question="TestBrand 是什么？",
            answer_text="TestBrand 是一家金融公司", status="success",
            collected_at=datetime.utcnow(),
        )
        db_session.add(qr)
        await db_session.flush()

        h = HallucinationResult(
            brand_id=brand.id,
            query_result_id=qr.id,
            collection_run_id=run.id,
            field_name=field_name, field_level=severity,
            severity=severity, verdict="incorrect",
            ai_claim="金融公司", ground_truth_value="Tech",
        )
        db_session.add(h)
    await db_session.commit()

    return org, brand, run


@pytest.mark.asyncio
async def test_generate_insights_cross_platform_p0(db_session):
    """同一 GT 字段在 3 平台都错 → severity=P0, confidence=high."""
    org, brand, run = await _seed_insight_data(
        db_session, ["deepseek", "kimi", "doubao"], field_name="industry", severity="P0",
    )

    insight = await generate_insights(str(run.id), str(brand.id), str(org.id), db_session)
    assert insight is not None
    findings = insight["key_findings_json"]
    p0_findings = [f for f in findings if f["severity"] == "P0"]
    assert len(p0_findings) >= 1
    cross_platform = [f for f in p0_findings if f["type"] == "cross_platform_p0_error"]
    assert len(cross_platform) >= 1
    assert cross_platform[0]["confidence"] == "high"


@pytest.mark.asyncio
async def test_generate_insights_confidence_medium(db_session):
    """2 平台同类问题 → confidence=medium."""
    org, brand, run = await _seed_insight_data(
        db_session, ["deepseek", "kimi"], field_name="industry", severity="P1",
    )

    insight = await generate_insights(str(run.id), str(brand.id), str(org.id), db_session)
    p1_findings = [f for f in insight["key_findings_json"] if f["severity"] == "P1"]
    assert len(p1_findings) >= 1
    assert p1_findings[0]["confidence"] in ("medium", "high")


@pytest.mark.asyncio
async def test_generate_insights_confidence_low(db_session):
    """1 平台问题 → confidence 不为 high."""
    org, brand, run = await _seed_insight_data(
        db_session, ["deepseek"], field_name="industry", severity="P2",
    )

    insight = await generate_insights(str(run.id), str(brand.id), str(org.id), db_session)
    assert insight["confidence_level"] in ("medium", "low")
