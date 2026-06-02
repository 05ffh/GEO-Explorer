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

import yaml
from pathlib import Path

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
            "kpi_cards": _build_kpi_cards(sov, frr, acc, comp, cit, sr, ss, df, cpc, rq),
        },
    )
    db.add(snapshot)
    await db.commit()

    # Hallucination detection + Action plans
    try:
        await _run_hallucination_detection(brand_id, collection_run_id, org_id, db)
    except Exception:
        logger.exception("Hallucination detection failed for collection %s", collection_run_id)

    # ── Phase A: Build ReportQualitySummary and compute publishable ──
    try:
        from src.analyzer.quality import build_report_quality_summary, compute_report_publishable
        from src.models.collection_run import CollectionRun as CR
        from src.models.hallucination import HallucinationResult as HR

        run_row = await db.get(CR, collection_run_id)
        if run_row:
            quality_summary = await build_report_quality_summary(
                collection_run_id=str(collection_run_id),
                template_health=run_row.template_health_report_json or None,
                coverage_report=run_row.coverage_report_json or None,
                db=db,
            )

            # P0_MISSING_GT_EVIDENCE check
            from sqlalchemy import and_ as _and
            p0_rows = (await db.execute(
                select(HR).where(_and(
                    HR.collection_run_id == collection_run_id,
                    HR.verdict == "contradicted",
                    HR.severity == "P0",
                    HR.subject_type == "target_brand",
                ))
            )).scalars().all()
            for r in p0_rows:
                if not r.claim_text or not r.matched_gt_field or not r.reason or not r.ground_truth_value:
                    quality_summary["blocking_reasons"].append({
                        "code": "P0_MISSING_GT_EVIDENCE",
                        "message": "P0 hallucination 缺少 GT evidence",
                        "severity": "block",
                    })
                    break

            metric_results_dict = {}
            if snapshot:
                metric_results_dict = snapshot.details or {}

            publishable, blocking_reasons = compute_report_publishable(
                template_health=run_row.template_health_report_json or None,
                coverage_report=run_row.coverage_report_json or None,
                quality_summary=quality_summary,
                metric_results=metric_results_dict,
            )
            quality_summary["report_publishable"] = publishable
            quality_summary["blocking_reasons"] = blocking_reasons

            # Pydantic validate
            from src.analyzer.schemas import ReportQualitySummaryModel
            try:
                ReportQualitySummaryModel.model_validate(quality_summary)
            except Exception as e:
                logger.error("ReportQualitySummary schema validation failed: %s", e)
                quality_summary["report_publishable"] = False
                quality_summary["blocking_reasons"].append({
                    "code": "SCHEMA_VALIDATION_FAILED",
                    "message": str(e)[:200],
                    "severity": "block",
                })

            run_row.report_quality_summary_json = quality_summary
            run_row.report_publishable = publishable
            run_row.blocking_reasons_json = blocking_reasons
            db.add(run_row)
            await db.commit()
    except Exception:
        logger.exception("Quality module failed for collection %s", collection_run_id)

    from src.analyzer.insights import generate_insights
    try:
        await generate_insights(collection_run_id, brand_id, org_id, db)
    except Exception:
        logger.exception("Insight generation failed for collection %s", collection_run_id)

    # Unified report delivery (diagnostic + optimization 3-format + content pieces)
    try:
        from src.reports import deliver_all_reports
        brand = (await db.execute(select(Brand).where(Brand.id == brand_id))).scalar_one_or_none()
        bname = brand.name if brand else "Unknown"
        result = await deliver_all_reports(bname, brand_id, collection_run_id, db)
        logger.info("Reports delivered to %s", result.get("dir"))
    except Exception:
        logger.exception("Report delivery failed for collection %s", collection_run_id)

    return snapshot


def _build_kpi_cards(sov, frr, acc, comp, cit, sr, ss, df, cpc, rq) -> list[dict]:
    """Build KPI explainability cards with numerator/denominator/confidence."""
    from src.schemas.ground_truth import KPI_DISPLAY_NAMES
    kpi_data = [
        ("sov", sov), ("first_rec_rate", frr), ("accuracy_rate", acc),
        ("completeness_rate", comp), ("citation_rate", cit),
        ("scenario_recall", sr), ("semantic_stability", ss),
        ("differentiation", df), ("cross_platform_consistency", cpc),
        ("recommendation_quality", rq),
    ]
    cards = []
    for key, data in kpi_data:
        name = KPI_DISPLAY_NAMES.get(key, key)
        value = data.get("sov") or data.get("first_rec_rate") or data.get("accuracy_rate") or \
                data.get("completeness_rate") or data.get("citation_rate") or data.get("value", 0)
        cards.append({
            "key": key, "name_cn": name, "value": value,
            "numerator": data.get("numerator", 0), "denominator": data.get("denominator", 0),
            "sample_size": data.get("sample_size", 0), "confidence": data.get("confidence", "low"),
        })
    return cards


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

    from src.analyzer.hallucination import HallucinationDetector, check_template_render_status
    from src.models.query_template import QueryTemplate as QT

    brand_row = (await db.execute(
        select(Brand).where(Brand.id == brand_id)
    )).scalar_one_or_none()
    bname = brand_row.name if brand_row else ""
    bindustry = brand_row.industry if brand_row else ""

    template_ids = list({qr.template_id for qr in query_results})
    template_rows = (await db.execute(
        select(QT).where(QT.id.in_(template_ids))
    )).scalars().all()
    template_map = {t.id: t for t in template_rows}

    gt_json_r = gt.ground_truth_json if gt else None
    template_render_status = {}
    for tid, tmpl in template_map.items():
        template_render_status[tid] = check_template_render_status(
            tmpl.template_text,
            brand_name=bname,
            brand_industry=bindustry,
            gt_json=gt_json_r,
        )

    detector = HallucinationDetector()
    all_hallucinations = []

    for qr in query_results:
        try:
            render_status = template_render_status.get(qr.template_id, "ok")
            results = await detector.detect(qr, gt, db, render_status=render_status)
            for h in results:
                db.add(h)
            all_hallucinations.extend(results)
        except Exception:
            logger.warning("Hallucination detection failed for query %s", qr.id)

    await db.flush()

    # Generate action plans from hallucinations
    incorrect_hallucinations = [h for h in all_hallucinations if h.verdict == "contradicted"]
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

    if incorrect_hallucinations:
        await _cluster_action_themes(brand_id, org_id, collection_run_id,
                                     all_hallucinations, incorrect_hallucinations, db)


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

            # Determine risk level from source fields
            from src.schemas.ground_truth import FIELD_RISK_LEVELS
            risk = "low"
            for field in theme_def["fields"]:
                for level, fields in FIELD_RISK_LEVELS.items():
                    if field in fields and level == "high":
                        risk = "high"
                        break
                if risk == "high":
                    break
                for level, fields in FIELD_RISK_LEVELS.items():
                    if field in fields and level == "medium" and risk == "low":
                        risk = "medium"

            initial_status = "needs_review" if risk in ("high", "medium") else "fact_checked"

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
                risk_level=risk,
                status=initial_status,
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


async def _cluster_action_themes(brand_id, org_id, collection_run_id,
                                  all_hallucinations, incorrect_hallucinations, db):
    """Cluster action plans into ActionThemes by field + error_type + severity."""
    from src.models.action_theme import ActionTheme
    from collections import defaultdict

    # Group by (field, severity)
    clusters = defaultdict(list)
    for h in incorrect_hallucinations:
        key = (h.field_name, h.severity)
        clusters[key].append(h)

    # Create one theme per cluster, limit to 10 themes
    theme_count = 0
    for (field_name, severity), hall_group in sorted(clusters.items(),
                                                       key=lambda x: len(x[1]), reverse=True):
        if theme_count >= 10:
            break

        platforms = list(set(h.query_result.platform if hasattr(h, 'query_result') else "unknown"
                             for h in hall_group))
        claims = [h.ai_claim[:200] for h in hall_group[:3]]
        h_ids = [str(h.id) for h in hall_group]

        theme = ActionTheme(
            organization_id=org_id, brand_id=brand_id,
            collection_run_id=collection_run_id,
            title=f"{'P0' if severity == 'P0' else 'P1' if severity == 'P1' else 'P2'} {field_name} 优化",
            priority=severity,
            issue_type="incorrect_claim",
            affected_fields=[field_name],
            affected_platforms=platforms,
            hallucination_result_ids=h_ids,
            action_plan_ids=[],
            evidence_summary={"field": field_name, "error_count": len(hall_group)},
            typical_ai_claims=claims,
            recommended_content_types=["FAQ", "Organization"],
            expected_kpi_impact={"accuracy_rate": "+10%"},
            effort_level="medium" if len(hall_group) < 50 else "high",
            status="detected",
        )
        db.add(theme)
        theme_count += 1

    await db.commit()
    logger.info("Action themes clustered: %d themes from %d action plans",
                theme_count, len(incorrect_hallucinations))
