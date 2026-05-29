import logging
from datetime import date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.ground_truth import GroundTruthVersion
from src.models.query_result import QueryResult
from src.models.action_plan import ActionPlan
from src.models.brand import Brand
from src.actions.executor import _generate_with_llm
from src.analyzer.sov import compute_sov
from src.analyzer.first_rec import compute_first_rec
from src.analyzer.accuracy import compute_accuracy
from src.analyzer.completeness import compute_completeness
from src.analyzer.citation import compute_citation_rate
from src.analyzer.scenario_recall import compute_scenario_recall
from src.analyzer.semantic_stability import compute_semantic_stability
from src.analyzer.differentiation import compute_differentiation
from src.analyzer.cross_platform_consistency import compute_cross_platform_consistency
from src.analyzer.recommendation_quality import compute_recommendation_quality

logger = logging.getLogger(__name__)


async def compute_and_save_metrics(
    brand_id: str, org_id: str, collection_run_id: str, db: AsyncSession,
) -> MetricsSnapshot:
    sov = await compute_sov(brand_id, collection_run_id, db)
    frr = await compute_first_rec(brand_id, collection_run_id, db)
    acc = await compute_accuracy(brand_id, collection_run_id, db)
    comp = await compute_completeness(brand_id, collection_run_id, db)
    cit = await compute_citation_rate(brand_id, collection_run_id, db)

    sr = await compute_scenario_recall(brand_id, collection_run_id, db)
    ss = await compute_semantic_stability(brand_id, collection_run_id, db)
    df = await compute_differentiation(brand_id, collection_run_id, db)
    cpc = await compute_cross_platform_consistency(brand_id, collection_run_id, db)
    rq = await compute_recommendation_quality(brand_id, collection_run_id, db)

    snapshot = MetricsSnapshot(
        brand_id=brand_id, organization_id=org_id,
        collection_run_id=collection_run_id,
        week_start=date.today(),
        sov=sov["sov"],
        first_rec_rate=frr["first_rec_rate"],
        accuracy_rate=acc["accuracy_rate"],
        completeness_rate=comp["completeness_rate"],
        citation_rate=cit["citation_rate"],
        sample_size=sov["sample_size"],
        failure_rate=sov["failure_rate"],
        details={
            "sov": sov, "frr": frr, "accuracy": acc, "completeness": comp, "citation": cit,
            "extended_kpis": {
                "scenario_recall": sr,
                "semantic_stability": ss,
                "differentiation": df,
                "cross_platform_consistency": cpc,
                "recommendation_quality": rq,
            },
        },
    )
    db.add(snapshot)
    await db.commit()

    # Hallucination detection + Action plans
    try:
        await _run_hallucination_detection(brand_id, collection_run_id, org_id, db)
    except Exception:
        logger.exception("Hallucination detection failed for collection %s", collection_run_id)

    from src.analyzer.insights import generate_insights
    try:
        await generate_insights(collection_run_id, brand_id, org_id, db)
    except Exception:
        logger.exception("Insight generation failed for collection %s", collection_run_id)

    # Auto-generate reports (3 formats: .md + .pdf + .docx)
    try:
        from src.reports.diagnostic import generate_diagnostic_report
        from src.reports.action_plan import generate_optimization_plan
        from src.models.brand import Brand
        brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
        brand_name = brand.name if brand else "Unknown"
        await generate_diagnostic_report(brand_name, collection_run_id, brand_id, db)
        await generate_optimization_plan(brand_name, collection_run_id, brand_id, db)
        logger.info("Reports generated for collection %s", collection_run_id)
    except Exception:
        logger.exception("Report generation failed for collection %s", collection_run_id)

    # Auto-generate Content Packages from top P0 action plans
    try:
        await _generate_content_packages(brand_id, org_id, db)
    except Exception:
        logger.exception("Content package generation failed for collection %s", collection_run_id)

    # Export Content Packages as deliverable files
    try:
        from src.reports.content_export import export_content_packages
        brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
        bname = brand.name if brand else "Unknown"
        await export_content_packages(bname, brand_id, db)
        logger.info("Content packages exported for brand %s", bname)
    except Exception:
        logger.exception("Content package export failed for collection %s", collection_run_id)

    return snapshot


async def _run_hallucination_detection(
    brand_id: str, collection_run_id: str, org_id: str, db: AsyncSession,
) -> None:
    """Run hallucination detection on all query results and generate action plans."""
    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalar_one_or_none()
    if not gt:
        logger.info("No active GT for brand %s, skipping hallucination detection", brand_id)
        return

    query_results = (await db.execute(
        select(QueryResult).where(
            QueryResult.collection_run_id == collection_run_id,
            QueryResult.status == "success",
        )
    )).scalars().all()

    if not query_results:
        return

    from src.analyzer.hallucination import HallucinationDetector
    detector = HallucinationDetector()
    all_hallucinations = []

    for qr in query_results:
        try:
            results = await detector.detect(qr, gt, db)
            for h in results:
                db.add(h)
            all_hallucinations.extend(results)
        except Exception:
            logger.warning("Hallucination detection failed for query %s", qr.id)

    await db.flush()

    # Generate action plans from hallucinations
    incorrect_hallucinations = [h for h in all_hallucinations if h.verdict == "incorrect"]
    if incorrect_hallucinations:
        TRIGGER_MAP = {
            "P0": {"action_type": "definition_correction", "content_type": "FAQ"},
            "P1": {"action_type": "authority_building", "content_type": "Q&A"},
            "P2": {"action_type": "content_enrichment", "content_type": "Tutorial"},
        }
        for h in incorrect_hallucinations:
            trigger = TRIGGER_MAP.get(h.severity, TRIGGER_MAP["P2"])
            plan = ActionPlan(
                brand_id=brand_id,
                organization_id=org_id,
                trigger_type=f"field_{h.field_name}_error",
                action_type=trigger["action_type"],
                priority=h.severity,
                evidence_hallucination_ids=[str(h.id)],
                ai_wrong_claims={"claim": h.ai_claim},
                correct_ground_truth={"field": h.field_name, "value": str(h.ground_truth_value)},
                suggested_content_type=trigger["content_type"],
                acceptance_criteria=(
                    f"Field '{h.field_name}' hallucination resolved: "
                    f"AI should state '{str(h.ground_truth_value)[:100]}'"
                ),
                status="pending",
            )
            db.add(plan)

    await db.commit()
    logger.info("Hallucination detection complete: %d claims, %d incorrect, %d action plans",
                len(all_hallucinations), len(incorrect_hallucinations),
                len(incorrect_hallucinations))


async def _generate_content_packages(
    brand_id: str, org_id: str, db: AsyncSession,
) -> None:
    """Generate rich Content Packages by grouping action plans into content themes."""
    from src.models.content_package import ContentPackage
    from collections import Counter

    gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active",
        )
    )).scalar_one_or_none()
    if not gt:
        return

    brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
    brand_name = brand.name if brand else "Unknown"
    gt_json = gt.ground_truth_json

    # Field → Content Theme mapping: group related fields into coherent content pieces
    CONTENT_THEMES = [
        {
            "theme": "品牌介绍 (About)",
            "content_type": "Organization",
            "fields": ["official_name", "industry", "category", "subcategory", "positioning"],
            "prompt_template": (
                "你是一个品牌内容专家。基于以下品牌事实信息，撰写一篇 500-800 字的品牌介绍页面内容。"
                "内容应包括：品牌背景、所属行业与品类、核心定位与使命。"
                "使用专业但友好的语调。只使用提供的事实。标注引用来源。\n\n品牌: {brand}\n事实: {facts}"
            ),
            "publish_target": "官网 /about 页面",
        },
        {
            "theme": "产品与服务 (Products)",
            "content_type": "FAQ",
            "fields": ["core_products", "core_features"],
            "prompt_template": (
                "你是一个产品内容专家。基于以下品牌事实，撰写一套 FAQ 格式的产品介绍内容（至少 3 个问题）。"
                "包含：核心产品有哪些、产品特点、与竞品的区别。"
                "专业且客观。只使用提供的事实。\n\n品牌: {brand}\n事实: {facts}"
            ),
            "publish_target": "官网 /products 或 /faq 页面",
        },
        {
            "theme": "用户与场景 (Users & Scenarios)",
            "content_type": "FAQ",
            "fields": ["target_users", "best_fit_users", "core_scenarios", "scenario_keywords"],
            "prompt_template": (
                "你是一个用户运营内容专家。基于以下品牌事实，撰写一套面向潜在客户的 FAQ（至少 3 个问题）。"
                "说明：目标用户是谁、在什么场景下选择这个品牌最合适、解决了什么问题。"
                "实用且有说服力。只使用提供的事实。\n\n品牌: {brand}\n事实: {facts}"
            ),
            "publish_target": "官网 /why-us 或场景推荐页面",
        },
        {
            "theme": "竞争优势 (Differentiation)",
            "content_type": "FAQ",
            "fields": ["key_differentiators", "target_competitors", "alternative_solutions"],
            "prompt_template": (
                "你是一个市场分析内容专家。基于以下品牌事实，撰写一份客观的竞品对比 FAQ（至少 3 个问题）。"
                "说明：与主要竞品相比的不同之处、替代方案有哪些、为什么选择该品牌。"
                "客观公正，不做虚假比较。只使用提供的事实。\n\n品牌: {brand}\n事实: {facts}"
            ),
            "publish_target": "官网 /compare 或竞品对比页面",
        },
    ]

    from src.actions.fact_checker import check_content_against_gt
    from src.actions.schema_generator import generate_jsonld

    generated = 0
    for theme_def in CONTENT_THEMES:
        # Collect GT facts for this theme's fields
        facts = {}
        for field in theme_def["fields"]:
            if field in gt_json:
                val = gt_json[field]
                facts[field] = str(val)[:500] if not isinstance(val, list) else ", ".join(str(x) for x in val)

        if not facts:
            continue

        try:
            # Generate rich content via LLM
            facts_text = "\n".join(f"- {k}: {v}" for k, v in facts.items())
            prompt = theme_def["prompt_template"].format(brand=brand_name, facts=facts_text)

            content_body = await _generate_with_llm(prompt, theme_def["content_type"])

            content_items = [{
                "type": theme_def["content_type"],
                "theme": theme_def["theme"],
                "title": f"{brand_name} - {theme_def['theme']}",
                "body": content_body,
                "source_fields": list(facts.keys()),
            }]

            # Fact check
            fact_report = check_content_against_gt(content_items, gt_json)

            # Schema.org
            schema = generate_jsonld(brand_name, gt_json, theme_def["content_type"])

            # Find representative action plan for this theme
            rep_plan = (await db.execute(
                select(ActionPlan).where(
                    ActionPlan.brand_id == brand_id,
                    ActionPlan.priority.in_(["P0", "P1"]),
                    ActionPlan.status == "pending",
                ).limit(1)
            )).scalar_one_or_none()

            pkg = ContentPackage(
                action_plan_id=rep_plan.id if rep_plan else None,
                organization_id=org_id,
                brand_id=brand_id,
                content_items=content_items,
                schema_items=schema["schemas"],
                publishing_checklist=[
                    {"item": f"发布目标: {theme_def['publish_target']}", "checked": False},
                    {"item": "所有事实与 GT 一致", "checked": fact_report["overall_pass"]},
                    {"item": "禁止性表述（领先/第一/最大）已检查", "checked": fact_report["issues_found"] == 0},
                    {"item": "Schema.org JSON-LD 格式有效", "checked": len(schema["schemas"]) > 0},
                    {"item": "内容经人工审核确认", "checked": False},
                ],
                fact_check_report=fact_report,
                status="draft",
            )
            db.add(pkg)
            generated += 1

        except Exception as e:
            logger.warning("Content package failed for theme %s: %s", theme_def["theme"], e)

    # Mark processed P0 plans
    (await db.execute(
        __import__('sqlalchemy').update(ActionPlan).where(
            ActionPlan.brand_id == brand_id,
            ActionPlan.priority == "P0",
            ActionPlan.status == "pending",
        ).values(status="in_progress")
    ))
    await db.commit()
    logger.info("Content packages generated: %d themes", generated)
