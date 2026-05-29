import pytest


def test_fact_checker_detects_forbidden_terms():
    from src.actions.fact_checker import check_content_against_gt
    gt = {"official_name": "TestBrand", "positioning": "A test platform"}
    content = [{"type": "FAQ", "body": "TestBrand 是行业领先的最大平台"}]
    report = check_content_against_gt(content, gt)
    assert report["issues_found"] > 0
    assert any("领先" in r.get("forbidden_terms", []) for r in report["items"] if "领先" in str(r))
    # At least one item should have forbidden_terms
    assert report["items"][0]["forbidden_terms"]


def test_fact_checker_passes_clean_content():
    from src.actions.fact_checker import check_content_against_gt
    gt = {"official_name": "TestBrand", "positioning": "A test platform"}
    content = [{"type": "FAQ", "body": "TestBrand 是一个测试平台，提供测试服务"}]
    report = check_content_against_gt(content, gt)
    assert report["overall_pass"] is True
    assert report["issues_found"] == 0


def test_schema_generator_faq():
    from src.actions.schema_generator import generate_jsonld
    gt = {"official_name": "TestBrand", "positioning": "测试平台", "core_products": "测试产品"}
    result = generate_jsonld("TestBrand", gt, "FAQ")
    assert "schemas" in result
    assert "json_ld" in result
    schema = result["schemas"][0]
    assert schema["@type"] == "FAQPage"
    assert len(schema["mainEntity"]) > 0


def test_schema_generator_organization():
    from src.actions.schema_generator import generate_jsonld
    gt = {"official_name": "TestBrand", "positioning": "测试平台", "official_domains": "test.com"}
    result = generate_jsonld("TestBrand", gt, "Organization")
    schema = result["schemas"][0]
    assert schema["@type"] == "Organization"
    assert schema["name"] == "TestBrand"


def test_content_package_export():
    from src.actions.content_package import export_content_package
    from unittest.mock import MagicMock
    pkg = MagicMock()
    pkg.content_items = [{"type": "FAQ", "title": "FAQ", "body": "Test content"}]
    pkg.schema_items = [{"@type": "FAQPage"}]
    pkg.publishing_checklist = [{"item": "Check 1", "checked": False}]
    pkg.fact_check_report = {"overall_pass": True}
    pkg.status = "draft"
    result = export_content_package(pkg)
    assert "markdown" in result
    assert "json_ld" in result
    assert "checklist" in result
    assert result["status"] == "draft"


@pytest.mark.asyncio
async def test_content_package_requires_active_gt(db_session):
    """ContentPackage creation fails when no active GT exists."""
    from src.models.organization import Organization
    from src.models.brand import Brand
    from src.models.action_plan import ActionPlan

    org = Organization(name="TestOrg")
    db_session.add(org)
    await db_session.commit()
    brand = Brand(organization_id=org.id, name="TestBrand", industry="Tech")
    db_session.add(brand)
    await db_session.commit()
    plan = ActionPlan(
        brand_id=brand.id,
        organization_id=org.id,
        trigger_type="test",
        action_type="test",
    )
    db_session.add(plan)
    await db_session.commit()

    from src.actions.content_package import build_content_package
    with pytest.raises(ValueError, match="No active Ground Truth"):
        await build_content_package(
            str(plan.id), str(brand.id), str(org.id),
            [{"type": "FAQ", "body": "test"}],
            [{"@type": "FAQPage"}],
            {"overall_pass": True},
            db_session,
        )
