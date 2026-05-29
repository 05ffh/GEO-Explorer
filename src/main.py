from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.database import get_db
from src.api.deps import get_current_user, get_org_brand_or_404
from src.models.user import User
from src.models.brand import Brand
from src.api import auth, brands, metrics, collection_runs, hallucinations, actions, dashboard, ground_truth
from src.schemas.ground_truth import KPI_DISPLAY_NAMES

app = FastAPI(title="GEO Explorer", version="0.1.0")
app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")

for router in [
    auth.router, brands.router, metrics.router,
    collection_runs.router, hallucinations.router,
    actions.router, dashboard.router, ground_truth.router,
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
                  collection_time: str = "", **extra) -> dict:
    """Build template context with all required sidebar/nav variables."""
    return {
        "request": request,
        "current_page": current_page,
        "brands": brands,
        "current_brand_id": current_brand_id,
        "current_brand_name": current_brand_name,
        "collection_time": collection_time,
        "KPI_DISPLAY_NAMES": KPI_DISPLAY_NAMES,
        **extra,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


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
        return templates.TemplateResponse("dashboard/index.html", _page_context(
            request, "dashboard", org_brands,
            current_brand_id=first["id"], current_brand_name=first["name"],
            vm=_empty_dashboard_vm(first["id"], first["name"]),
        ))
    return templates.TemplateResponse("dashboard/index.html", _page_context(
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
    return templates.TemplateResponse("dashboard/index.html", _page_context(
        request, "dashboard", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        collection_time=vm["data_reliability"]["latest_snapshot_at"] or "",
        vm=vm,
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
    return templates.TemplateResponse("gt_review/index.html", _page_context(
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
    return templates.TemplateResponse("evidence/index.html", _page_context(
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
    return templates.TemplateResponse("hallucinations/index.html", _page_context(
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
    return templates.TemplateResponse("actions/index.html", _page_context(
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
    return templates.TemplateResponse("content/index.html", _page_context(
        request, "content", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        vm=vm,
    ))


@app.get("/brands/{brand_id}/trends", response_class=HTMLResponse)
async def trends_page(request: Request, brand_id: str,
                      user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    """Trends & attribution page."""
    brand = await get_org_brand_or_404(brand_id, user, db)
    from src.view_models.trends import build_trends_vm
    vm = await build_trends_vm(brand, "month", user, db)
    org_brands = await _get_org_brands(user, db)
    return templates.TemplateResponse("trends/index.html", _page_context(
        request, "trends", org_brands,
        current_brand_id=str(brand.id), current_brand_name=brand.name,
        vm=vm,
    ))
