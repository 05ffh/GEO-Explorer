"""GEO Explorer — Trends & Attribution ViewModel.

Answers: "Did publishing content actually improve AI perception of the brand?"
Pre-computes trend charts data, event markers, and attribution analysis.
"""
from datetime import timedelta

from sqlalchemy import select, desc
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.collection_run import CollectionRun
from src.models.action_theme import ActionTheme
from src.models.content_package import ContentPackage
from src.models.ground_truth import GroundTruthVersion
from src.schemas.ground_truth import KPI_DISPLAY_NAMES

ALL_KPI_KEYS = [
    "sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate",
    "scenario_recall", "semantic_stability", "differentiation",
    "cross_platform_consistency", "recommendation_quality",
]

# P0-3: pre/post window configuration
PRE_WINDOW_DAYS = 14
POST_WINDOW_DAYS = 14
ABSORPTION_LAG_DAYS = 7
MIN_PRE_SNAPSHOTS = 2
MIN_POST_SNAPSHOTS = 2


def get_kpi_value(snapshot: MetricsSnapshot, kpi_key: str) -> float:
    """Read KPI value — ORM column for 5 core KPIs, details.extended_kpis for 5 extended."""
    if kpi_key in ("sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate"):
        return getattr(snapshot, kpi_key, 0.0) or 0.0
    ek = (snapshot.details or {}).get("extended_kpis", {})
    val = ek.get(kpi_key)
    return val.get("value", 0.0) if isinstance(val, dict) else 0.0


def get_kpi_threshold(kpi_key: str) -> float:
    """P0-6: minimum meaningful change threshold per KPI."""
    thresholds = {
        "sov": 0.05, "first_rec_rate": 0.05, "accuracy_rate": 0.05,
        "completeness_rate": 0.05, "citation_rate": 0.03,
        "scenario_recall": 0.05, "semantic_stability": 0.05,
        "differentiation": 0.05, "cross_platform_consistency": 0.05,
        "recommendation_quality": 0.03,
    }
    return thresholds.get(kpi_key, 0.05)


def infer_target_kpi(theme: ActionTheme) -> list[str]:
    """P0-7: infer target KPI from expected_kpi_impact or issue_type mapping."""
    impact = theme.expected_kpi_impact or {}
    if isinstance(impact, dict):
        keys = [k for k in impact if k in ALL_KPI_KEYS]
        if keys:
            return keys[:3]
    mapping = {
        "citation_low": ["citation_rate"],
        "accuracy_low": ["accuracy_rate"],
        "completeness_low": ["completeness_rate"],
        "scenario_missing": ["scenario_recall"],
        "differentiation_missing": ["differentiation"],
        "recommendation_weak": ["recommendation_quality"],
    }
    return mapping.get(theme.issue_type, ["accuracy_rate"])


def compute_attribution(pre_avg: float, post_avg: float, sample_size: int,
                        has_confounders: bool, change: float, threshold: float) -> dict:
    """P0-5: structured attribution result with label_key, confidence, reason."""
    if sample_size < 4:
        return {
            "label_key": "insufficient_sample", "label_cn": "样本不足",
            "confidence": "low",
            "reason": f"仅 {sample_size} 个采集快照，不足以判断效果。需要更多数据。",
            "needs_more_data": True,
        }
    if has_confounders:
        return {
            "label_key": "confounded", "label_cn": "存在混淆因素",
            "confidence": "low",
            "reason": "归因窗口内检测到 GT/Prompt/平台变化，KPI 变动可能受混淆因素影响。",
            "needs_more_data": True,
        }
    if abs(change) < threshold:
        direction_label = "提升" if change > 0 else "下降"
        return {
            "label_key": "no_obvious_effect", "label_cn": "无明显效果",
            "confidence": "medium",
            "reason": f"变化 {abs(change)*100:.1f}% 低于最小阈值 {threshold*100:.0f}%，{direction_label}可能只是随机波动。",
            "needs_more_data": True,
        }
    if change > threshold:
        return {
            "label_key": "possible_action_effect", "label_cn": "可能由 Action 导致",
            "confidence": "medium",
            "reason": f"发布后提升 {change*100:.1f} 个百分点，超过阈值 {threshold*100:.0f}%。同期未检测到混淆因素。",
            "needs_more_data": True,
        }
    return {
        "label_key": "negative_effect_possible", "label_cn": "可能存在负面效果",
        "confidence": "medium",
        "reason": f"发布后下降 {abs(change)*100:.1f} 个百分点。建议排查 Action 内容质量或外部事件。",
        "needs_more_data": True,
    }


async def _gt_changed_during(brand_id, date_from, date_to, db) -> bool:
    """Check if any GT version was promoted during the window."""
    result = await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
            GroundTruthVersion.status == "active",
            GroundTruthVersion.created_at >= date_from,
            GroundTruthVersion.created_at <= date_to,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _prompt_changed_during(brand_id, date_from, date_to, db) -> bool:
    """Check if prompt version changed during the window."""
    result = await db.execute(
        select(CollectionRun).where(
            CollectionRun.brand_id == brand_id,
            CollectionRun.started_at >= date_from,
            CollectionRun.started_at <= date_to,
        ).order_by(CollectionRun.started_at)
    )
    runs = result.scalars().all()
    prompt_ids = set()
    for r in runs:
        if r.prompt_version_id:
            prompt_ids.add(r.prompt_version_id)
    return len(prompt_ids) > 1


async def _build_events(brand_id, db) -> list:
    """Build event markers: GT versions, content publishes, prompt changes."""
    events = []

    gt_versions = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand_id,
        ).order_by(GroundTruthVersion.created_at)
    )).scalars().all()
    for gt in gt_versions:
        if gt.created_at:
            events.append({
                "type": "gt_update", "date": gt.created_at.isoformat()[:10],
                "label": f"GT v{gt.version}", "severity": "info",
            })

    pkgs = (await db.execute(
        select(ContentPackage).where(
            ContentPackage.brand_id == brand_id,
            ContentPackage.published_at.isnot(None),
            ContentPackage.publish_url != "",
        ).order_by(ContentPackage.published_at)
    )).scalars().all()
    for pkg in pkgs:
        events.append({
            "type": "content_published",
            "date": pkg.published_at.isoformat()[:10],
            "label": pkg.title or "Content Package", "severity": "info",
        })

    runs = (await db.execute(
        select(CollectionRun).where(
            CollectionRun.brand_id == brand_id,
            CollectionRun.prompt_version_id.isnot(None),
        ).order_by(CollectionRun.started_at)
    )).scalars().all()
    prev_pv = None
    for run in runs:
        if run.prompt_version_id and run.prompt_version_id != prev_pv and run.started_at:
            events.append({
                "type": "prompt_change",
                "date": run.started_at.isoformat()[:10],
                "label": "Prompt 变更", "severity": "warning",
            })
        prev_pv = run.prompt_version_id

    return sorted(events, key=lambda e: e["date"])


async def _build_attribution(brand_id, snapshots, db) -> list:
    """P0-2: build attribution table — pre/post KPI comparison per published Action."""
    if not snapshots:
        return []

    themes = (await db.execute(
        select(ActionTheme).where(
            ActionTheme.brand_id == brand_id,
            ActionTheme.status.in_(["published_marked", "verification_pending", "verified"]),
        ).order_by(ActionTheme.updated_at.desc())
    )).scalars().all()

    rows = []
    for theme in themes:
        pkgs = (await db.execute(
            select(ContentPackage).where(
                ContentPackage.action_theme_id == theme.id,
                ContentPackage.published_at.isnot(None),  # P0-1: must have published_at
            ).order_by(desc(ContentPackage.published_at))
        )).scalars().all()

        for pkg in pkgs:
            publish_dt = pkg.published_at
            if not publish_dt:
                continue

            # P0-3: window with absorption lag
            post_start = publish_dt + timedelta(days=ABSORPTION_LAG_DAYS)
            pre_start = publish_dt - timedelta(days=PRE_WINDOW_DAYS)

            pre = [s for s in snapshots
                   if s.week_start and pre_start <= s.week_start < publish_dt.date()]
            pre = pre[-MIN_PRE_SNAPSHOTS:] if len(pre) >= MIN_PRE_SNAPSHOTS else []

            post = [s for s in snapshots
                    if s.week_start and s.week_start >= post_start.date()]
            post = post[:MIN_POST_SNAPSHOTS] if len(post) >= MIN_POST_SNAPSHOTS else []

            if len(pre) < MIN_PRE_SNAPSHOTS or len(post) < MIN_POST_SNAPSHOTS:
                continue

            target_kpis = infer_target_kpi(theme)

            # P0-4: extended confounder detection
            date_from = pre[0].week_start if pre[0].week_start else publish_dt.date()
            date_to = post[-1].week_start if post[-1].week_start else publish_dt.date()
            confounders = []

            if await _gt_changed_during(brand_id, date_from, date_to, db):
                confounders.append({"type": "gt_update", "severity": "high",
                                    "detail": "GT 版本在归因窗口内变更"})
            if await _prompt_changed_during(brand_id, date_from, date_to, db):
                confounders.append({"type": "prompt_change", "severity": "high",
                                    "detail": "Prompt 模板在归因窗口内变更"})
            if any((s.failure_rate or 0) > 0.3 for s in post):
                confounders.append({"type": "platform_failure", "severity": "medium",
                                    "detail": "post 窗口部分平台失败率 > 30%"})

            for kpi_key in target_kpis[:3]:
                pre_vals = [get_kpi_value(s, kpi_key) for s in pre]
                post_vals = [get_kpi_value(s, kpi_key) for s in post]
                pre_avg = sum(pre_vals) / len(pre_vals)
                post_avg = sum(post_vals) / len(post_vals)
                change = post_avg - pre_avg
                threshold = get_kpi_threshold(kpi_key)
                sample_total = len(pre) + len(post)

                result = compute_attribution(
                    pre_avg, post_avg, sample_total,
                    bool(confounders), change, threshold,
                )

                rows.append({
                    "theme_id": str(theme.id),
                    "theme_title": theme.title,
                    "publish_date": publish_dt.isoformat()[:10],
                    "publish_url": pkg.publish_url or "",
                    "target_kpi": kpi_key,
                    "kpi_label": KPI_DISPLAY_NAMES.get(kpi_key, kpi_key),
                    "pre_avg": round(pre_avg, 4),
                    "post_avg": round(post_avg, 4),
                    "change": round(change, 4),
                    "change_display": f"{'+' if change > 0 else ''}{round(change * 100, 1)}%",
                    "is_meaningful": abs(change) >= threshold,
                    "threshold": threshold,
                    "sample_size": sample_total,
                    "pre_sample_size": len(pre),
                    "post_sample_size": len(post),
                    "label_key": result["label_key"],
                    "label_cn": result["label_cn"],
                    "confidence": result["confidence"],
                    "confounders": confounders,
                    "reason": result["reason"],
                    "needs_more_data": result["needs_more_data"],
                })

    return rows


async def build_trends_vm(brand, range_str, user, db) -> dict:
    """Build view model: dates, 10-KPI series, events, attribution table."""
    limit = {"week": 12, "month": 24, "quarter": 8}.get(range_str, 24)

    # P1-1: only completed analysis runs
    run_ids_result = await db.execute(
        select(CollectionRun.id).where(
            CollectionRun.brand_id == brand.id,
            CollectionRun.analysis_status == "completed",
        ).order_by(desc(CollectionRun.analysis_completed_at)).limit(limit)
    )
    run_ids = [r[0] for r in run_ids_result.all()]

    if not run_ids:
        return {
            "brand": {"id": str(brand.id), "name": brand.name},
            "dates": [], "series": {}, "events": [], "attribution": [],
            "range": range_str, "has_data": False,
        }

    snapshots = (await db.execute(
        select(MetricsSnapshot).where(
            MetricsSnapshot.collection_run_id.in_(run_ids),
            MetricsSnapshot.platform.is_(None),
            MetricsSnapshot.dimension.is_(None),
        ).order_by(MetricsSnapshot.week_start)
    )).scalars().all()

    dates = [s.week_start.isoformat()[:10] for s in snapshots]
    series = {}
    for kpi in ALL_KPI_KEYS:
        series[kpi] = [round(get_kpi_value(s, kpi), 4) for s in snapshots]

    events = await _build_events(brand.id, db)
    attribution = await _build_attribution(brand.id, snapshots, db)

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "dates": dates, "series": series, "events": events,
        "attribution": attribution, "range": range_str, "has_data": True,
    }
