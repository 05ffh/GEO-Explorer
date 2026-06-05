import os
from datetime import datetime, timezone
from fastapi import FastAPI, Request, Depends, Query
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from src.database import get_db
from src.config import settings
from src.api.deps import get_current_user, get_org_brand_or_404
from src.models.user import User
from src.models.brand import Brand
from src.api import auth, brands, metrics, collection_runs, hallucinations, actions, dashboard, ground_truth, tasks, publishing, saas, platform, template_versions, reclassifications, templates
from src.schemas.ground_truth import KPI_DISPLAY_NAMES

app = FastAPI(title="GEO Explorer", version="0.1.0")

# Request ID middleware for audit log linkage
from src.middleware.request_id import RequestIdMiddleware
app.add_middleware(RequestIdMiddleware)
app.mount("/static", StaticFiles(directory="src/static"), name="static")
tpl = Jinja2Templates(directory="src/templates")

for router in [
    auth.router, brands.router, metrics.router,
    collection_runs.router, hallucinations.router,
    actions.router, dashboard.router, ground_truth.router,
    tasks.router, publishing.router, saas.router, platform.router,
    template_versions.router, reclassifications.router, templates.router,
]:
    app.include_router(router)


async def _get_org_brands(user: User, db: AsyncSession):
    """Return brands list for sidebar selector."""
    result = await db.execute(
        select(Brand).where(Brand.organization_id == user.organization_id).order_by(Brand.name)
    )
    return [{"id": str(b.id), "name": b.name} for b in result.scalars().all()]


def _page_context(request: Request, current_page: str, brands: list,
                  current_brand_id: str = "", current_brand_name: str = "",
                  collection_time: str = "", user: User | None = None, **extra) -> dict:
    """Build template context with all required sidebar/nav variables."""
    is_admin = user is not None and user.platform_role in ("system_owner", "system_admin")
    return {
        "current_page": current_page,
        "brands": brands,
        "current_brand_id": current_brand_id,
        "current_brand_name": current_brand_name,
        "collection_time": collection_time,
        "KPI_DISPLAY_NAMES": KPI_DISPLAY_NAMES,
        "is_platform_admin": is_admin,
        **extra,
    }


def _render(request: Request, name: str, context: dict | None = None,
            status_code: int = 200) -> HTMLResponse:
    """Render a Jinja2 template. Sets is_platform_admin=False if not present."""
    ctx = context or {}
    ctx.setdefault("is_platform_admin", False)
    return tpl.TemplateResponse(request, name, ctx, status_code=status_code)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page — no auth required."""
    return _render(request, "auth/login.html")


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page — no auth required."""
    return _render(request, "auth/register.html")


@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request, user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """Onboarding page — after registration."""
    org_brands = await _get_org_brands(user, db)
    return _render(request, "auth/onboarding.html", _page_context(
        request, "onboarding", org_brands,
        user_email=user.email, user_name=user.name,
    ))


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Deep health check: app + DB + Redis."""
    import redis as redis_lib
    checks = {"app": "ok"}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
    try:
        r = redis_lib.from_url(settings.redis_url)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
    return checks


def _empty_dashboard_vm(brand_id: str = "", brand_name: str = "", industry: str = "") -> dict:
    """Minimal VM for empty/no-data dashboard state with all required keys."""
    return {
        "has_data": False,
        "brand": {"id": brand_id, "name": brand_name, "industry": industry},
        "kpi_cards": [],
        "health_score": 0, "health_label": "",
        "blocking_issues": [],
        "data_reliability": {"active_gt": False, "gt_coverage": 0, "pending_candidates": 0,
                              "latest_snapshot_at": None, "is_stale": False, "is_partial": False,
                              "platform_success_rate": 0, "collection_run_id": None},
        "top_risks": {"p0_hallucinations": 0, "p1_hallucinations": 0, "high_risk_content": 0},
        "priority_actions": [], "recent_changes": {},
        "permissions": {"can_trigger_collection": False, "can_review_gt": False,
                        "can_confirm_hallucination": False, "can_generate_content": False,
                        "can_approve_high_risk": False},
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(get_current_user),
                db: AsyncSession = Depends(get_db)):
    """Dashboard redirect — show first brand if available, otherwise empty state."""
    org_brands = await _get_org_brands(user, db)
    if org_brands:
        first = org_brands[0]
        return _render(request, "dashboard/index.html", _page_context(
            request, "dashboard", org_brands,
            current_brand_id=first["id"], current_brand_name=first["name"],
            vm=_empty_dashboard_vm(first["id"], first["name"]),
        ))
    return _render(request, "dashboard/index.html", _page_context(
        request, "dashboard", [],
        vm=_empty_dashboard_vm(),
    ))


@app.get("/brands/{brand_id}", response_class=HTMLResponse)
async def brand_dashboard(request: Request, brand_id: str,
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """Brand overview dashboard page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.dashboard import build_dashboard_vm
    vm = await build_dashboard_vm(brand, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "dashboard/index.html", _page_context(
        request, "dashboard", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        collection_time=vm["data_reliability"]["latest_snapshot_at"] or "",
        vm=vm, user=user,
    ))


# ── Module 1: Brand list + inline edit ───────────────────────────────────────

@app.get("/brands", response_class=HTMLResponse)
async def brand_list_page(request: Request, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db),
                           q: str = Query(default=""),
                           industry: str = Query(default=""),
                           page: int = Query(default=1, ge=1),
                           page_size: int = Query(default=20, ge=1, le=100)):
    from src.view_models.brands import build_brand_list_vm
    vm = await build_brand_list_vm(user, db, search_query=q, industry_filter=industry,
                                   page=page, page_size=page_size)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "brands/list.html", _page_context(
        request, "brand-list", org_brands, vm=vm, user=user,
    ))


@app.get("/brands/{brand_id}/edit", response_class=HTMLResponse)
async def brand_edit_fragment(request: Request, brand_id: str,
                                user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    brand = await get_org_brand_or_404(brand_id, user, db)
    industries = (await db.execute(
        select(Brand.industry).where(
            Brand.organization_id == user.organization_id, Brand.industry != "",
        ).distinct()
    )).scalars().all()
    defaults = ["餐饮连锁","银行","保险","金融科技","医疗健康","教育培训","汽车","零售","SaaS","科技","文旅"]
    opts = sorted(set(list(industries) + defaults))
    return _render(request, "partials/brand_header_edit.html", {
        "request": request,
        "vm": {"brand": {"id": str(brand.id), "name": brand.name, "industry": brand.industry or "",
                         "aliases": brand.aliases or []},
               "industry_options": [i for i in opts if i]},
    })


@app.get("/brands/{brand_id}/view", response_class=HTMLResponse)
async def brand_view_fragment(request: Request, brand_id: str,
                                user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    brand = await get_org_brand_or_404(brand_id, user, db)
    return _render(request, "partials/brand_header_view.html", {
        "request": request,
        "vm": {"brand": {"id": str(brand.id), "name": brand.name, "industry": brand.industry or "",
                         "aliases": brand.aliases or []}},
    })


# ── Module 2: Run list  ─────────────────────────────────────────────────────

@app.get("/brands/{brand_id}/runs", response_class=HTMLResponse)
async def run_list_page(request: Request, brand_id: str,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db),
                         page: int = Query(default=1, ge=1),
                         page_size: int = Query(default=20, ge=1, le=100)):
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.runs import build_run_list_vm
    vm = await build_run_list_vm(brand, user, db, page=page, page_size=page_size)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "runs/list.html", _page_context(
        request, "dashboard", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        vm=vm, vm_brand_id=str(brand.id), vm_brand_name=brand.name, user=user,
    ))


# ── Module 3: GT Compare ────────────────────────────────────────────────────

@app.get("/brands/{brand_id}/gt-compare", response_class=HTMLResponse)
async def gt_compare_page(request: Request, brand_id: str,
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.gt_compare import build_gt_compare_vm
    vm = await build_gt_compare_vm(brand, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "gt_review/compare.html", _page_context(
        request, "gt-review", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name, vm=vm, user=user,
    ))


@app.get("/brands/{brand_id}/gt-review", response_class=HTMLResponse)
async def gt_review_page(request: Request, brand_id: str,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    """GT review page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.gt_review import build_gt_review_vm
    vm = await build_gt_review_vm(brand, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "gt_review/index.html", _page_context(
        request, "gt-review", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        vm=vm,
    ))


@app.get("/brands/{brand_id}/evidence", response_class=HTMLResponse)
async def evidence_page(request: Request, brand_id: str,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """AI evidence page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.evidence import build_evidence_vm
    vm = await build_evidence_vm(brand, {}, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "evidence/index.html", _page_context(
        request, "evidence", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        vm=vm,
    ))


@app.get("/brands/{brand_id}/hallucinations", response_class=HTMLResponse)
async def hallucinations_page(request: Request, brand_id: str,
                              user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """Hallucination risk page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.hallucination import build_hallucination_vm
    vm = await build_hallucination_vm(brand, {}, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "hallucinations/index.html", _page_context(
        request, "hallucinations", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        vm=vm,
    ))


@app.get("/brands/{brand_id}/actions", response_class=HTMLResponse)
async def actions_page(request: Request, brand_id: str,
                       user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Action workbench page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.action import build_action_vm
    vm = await build_action_vm(brand, {}, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "actions/index.html", _page_context(
        request, "actions", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        vm=vm,
    ))


@app.get("/brands/{brand_id}/content", response_class=HTMLResponse)
async def content_page(request: Request, brand_id: str,
                       user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Content management page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.content import build_content_vm
    vm = await build_content_vm(brand, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "content/index.html", _page_context(
        request, "content", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        vm=vm,
    ))


@app.get("/brands/{brand_id}/trends", response_class=HTMLResponse)
async def trends_page(request: Request, brand_id: str,
                      range_str: str = Query("month", pattern="^(week|month|quarter)$"),
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """Trends & attribution page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.trends import build_trends_vm
    vm = await build_trends_vm(brand, range_str, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "trends/index.html", _page_context(
        request, "trends", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        vm=vm,
    ))


@app.get("/brands/{brand_id}/trends-fragment", response_class=HTMLResponse)
async def trends_fragment(request: Request, brand_id: str,
                          range_str: str = Query("month", pattern="^(week|month|quarter)$"),
                          user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """HTMX fragment — return _content.html only, no shell."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.trends import build_trends_vm
    vm = await build_trends_vm(brand, range_str, user, db)
    return _render(request, "trends/_content.html", {"vm": vm})


@app.get("/monitor/queue", response_class=HTMLResponse)
async def queue_monitor_page(request: Request,
                              user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """Queue monitor page — org-wide, not brand-specific."""
    from src.view_models.queue_monitor import build_queue_monitor_vm
    vm = await build_queue_monitor_vm(None, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "queue_monitor/index.html", _page_context(
        request, "queue-monitor", org_brands,
        vm=vm, current_page="queue-monitor",
    ))


@app.get("/publishing", response_class=HTMLResponse)
async def publishing_page(request: Request, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """Publishing management page."""
    org_brands = await _get_org_brands(user, db)
    from src.view_models.publishing import build_publishing_vm
    vm = await build_publishing_vm(user.organization_id, db)
    return _render(request, "publishing/index.html", _page_context(
        request, "publishing", org_brands, vm=vm, current_page="publishing",
    ))


@app.get("/saas/settings", response_class=HTMLResponse)
async def saas_settings_page(request: Request, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """SaaS settings page."""
    org_brands = await _get_org_brands(user, db)
    return _render(request, "saas/settings.html", _page_context(
        request, "saas", org_brands, current_page="saas",
    ))


@app.get("/saas/api-keys", response_class=HTMLResponse)
async def saas_api_keys_page(request: Request, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """API Keys management page."""
    org_brands = await _get_org_brands(user, db)
    return _render(request, "saas/api_keys.html", _page_context(
        request, "saas", org_brands, current_page="saas",
    ))


@app.get("/saas/members", response_class=HTMLResponse)
async def saas_members_page(request: Request, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    """Members management page."""
    org_brands = await _get_org_brands(user, db)
    return _render(request, "saas/members.html", _page_context(
        request, "saas", org_brands, current_page="saas",
    ))


@app.get("/saas/plans", response_class=HTMLResponse)
async def saas_plans_page(request: Request, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """Pricing/plans comparison page."""
    org_brands = await _get_org_brands(user, db)
    return _render(request, "saas/plans.html", _page_context(
        request, "saas", org_brands, current_page="saas",
    ))


@app.get("/saas/data", response_class=HTMLResponse)
async def saas_data_page(request: Request, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """Data export & deletion management page."""
    org_brands = await _get_org_brands(user, db)
    return _render(request, "saas/data.html", _page_context(
        request, "saas", org_brands, current_page="saas",
    ))


# ── Platform Console (system_admin+) ──────────────────────────────────────────

@app.get("/platform", response_class=HTMLResponse)
async def platform_overview_page(request: Request, user: User = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    """Platform overview dashboard."""
    from src.view_models.platform import build_platform_vm
    vm = await build_platform_vm(user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "platform/index.html", _page_context(
        request, "platform", org_brands, vm=vm))


@app.get("/platform/organizations", response_class=HTMLResponse)
async def platform_organizations_page(request: Request, user: User = Depends(get_current_user),
                                        db: AsyncSession = Depends(get_db)):
    """Organization management."""
    from src.view_models.platform import build_platform_vm
    vm = await build_platform_vm(user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "platform/organizations.html", _page_context(
        request, "platform-orgs", org_brands, vm=vm))


@app.get("/platform/plans", response_class=HTMLResponse)
async def platform_plans_page(request: Request, user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    """Plan management (system_owner only)."""
    from src.view_models.platform import build_platform_vm
    vm = await build_platform_vm(user, db)
    if not vm["visible_pages"]["plans"]:
        return _render(request, "platform/403.html", {}, status_code=403)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "platform/plans.html", _page_context(
        request, "platform-plans", org_brands, vm=vm))


@app.get("/platform/feature-flags", response_class=HTMLResponse)
async def platform_flags_page(request: Request, user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    """Feature flag management."""
    from src.view_models.platform import build_platform_vm
    vm = await build_platform_vm(user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "platform/feature_flags.html", _page_context(
        request, "platform-flags", org_brands, vm=vm))


@app.get("/platform/emergency-pause", response_class=HTMLResponse)
async def platform_pause_page(request: Request, user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    """Emergency pause management."""
    from src.view_models.platform import build_platform_vm
    vm = await build_platform_vm(user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "platform/emergency_pause.html", _page_context(
        request, "platform-pause", org_brands, vm=vm))


@app.get("/platform/audit-logs", response_class=HTMLResponse)
async def platform_audit_page(request: Request, user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    """Audit log viewer."""
    from src.view_models.platform import build_platform_vm
    vm = await build_platform_vm(user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "platform/audit_logs.html", _page_context(
        request, "platform-audit", org_brands, vm=vm))


@app.get("/platform/data-deletion", response_class=HTMLResponse)
async def platform_deletion_page(request: Request, user: User = Depends(get_current_user),
                                   db: AsyncSession = Depends(get_db)):
    """Data deletion approval (system_owner only)."""
    from src.view_models.platform import build_platform_vm
    vm = await build_platform_vm(user, db)
    if not vm["visible_pages"]["data_deletion"]:
        return _render(request, "platform/403.html", {}, status_code=403)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "platform/data_deletion.html", _page_context(
        request, "platform-deletion", org_brands, vm=vm))


@app.get("/brands/{brand_id}/reports", response_class=HTMLResponse)
async def reports_page(request: Request, brand_id: str,
                        user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    """Report download page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.reports import build_reports_vm
    vm = await build_reports_vm(brand, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "reports/index.html", _page_context(
        request, "reports", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name, vm=vm,
    ))


@app.post("/api/brands/{brand_id}/reports/generate")
async def generate_reports_api(brand_id: str,
                                body: dict,
                                user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    """Trigger report generation via async Celery task."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.reports.delivery import deliver_all_reports
    result = await deliver_all_reports(
        brand_name=brand.name,
        brand_id=str(brand.id),
        collection_run_id=body.get("collection_run_id", ""),
        db=db,
    )
    return {"status": "queued", "dir": result.get("dir"), **result}


@app.get("/api/brands/{brand_id}/reports/download")
async def download_report(brand_id: str,
                           artifact_id: str = Query(...),
                           user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    """Download a report artifact file."""
    from fastapi.responses import FileResponse
    from src.models.report_artifact import ReportArtifact
    import uuid

    artifact = await db.get(ReportArtifact, uuid.UUID(artifact_id))
    if not artifact or artifact.brand_id != uuid.UUID(brand_id):
        return {"detail": "Not found"}, 404

    # Increment download count
    artifact.download_count = (artifact.download_count or 0) + 1
    artifact.last_downloaded_at = datetime.now(timezone.utc)
    await db.commit()

    if not artifact.file_path or not os.path.exists(artifact.file_path):
        return {"detail": "File not found on disk"}, 404

    return FileResponse(artifact.file_path, filename=os.path.basename(artifact.file_path))


# ── Template Review Workbench (P2-3) ────────────────────────────────────────

@app.get("/templates", response_class=HTMLResponse)
async def templates_list_page(request: Request, user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db),
                               question_type: str | None = Query(None),
                               template_level: str | None = Query(None),
                               status: str | None = Query(None)):
    """Template list page."""
    from src.view_models.template_review import build_template_list_vm
    filters = {}
    if question_type: filters["question_type"] = question_type
    if template_level: filters["template_level"] = template_level
    if status: filters["status"] = status
    vm = await build_template_list_vm(user, db, filters)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "templates/index.html", _page_context(
        request, "templates", org_brands, vm=vm))


@app.get("/templates/new", response_class=HTMLResponse)
async def templates_new_page(request: Request, user: User = Depends(get_current_user)):
    """New template page — redirects to editor with empty template."""
    org_brands = await _get_org_brands(user, db=None)
    # Return a simple create form that POSTs to the API
    return _render(request, "templates/editor.html", _page_context(
        request, "templates", org_brands, vm={
            "error": "请使用 API POST /api/templates 创建模板，或从列表页点击「新建模板」",
        }))


@app.get("/templates/{template_id}", response_class=HTMLResponse)
async def templates_editor_page(request: Request, template_id: str,
                                  user: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db)):
    """Template editor page."""
    from src.view_models.template_review import build_template_editor_vm
    vm = await build_template_editor_vm(template_id, user, db)
    org_brands = await _get_org_brands(user, db)
    return _render(request, "templates/editor.html", _page_context(
        request, "templates", org_brands, vm=vm))
