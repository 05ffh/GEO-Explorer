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
            vm={"has_data": False, "brand": {"id": first["id"], "name": first["name"], "industry": ""}},
        ))
    return templates.TemplateResponse("dashboard/index.html", _page_context(
        request, "dashboard", [],
        vm={"has_data": False, "brand": {"id": "", "name": "", "industry": ""}},
    ))
