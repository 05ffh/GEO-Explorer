from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from src.api import auth, brands, metrics, collection_runs, hallucinations, actions, dashboard

app = FastAPI(title="GEO Explorer", version="0.1.0")
app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")

for router in [
    auth.router, brands.router, metrics.router,
    collection_runs.router, hallucinations.router,
    actions.router, dashboard.router,
]:
    app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("dashboard/index.html", {"request": request})
