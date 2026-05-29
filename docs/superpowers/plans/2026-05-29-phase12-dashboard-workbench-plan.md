# Phase 12: Dashboard 运营工作台 Implementation Plan v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 7-page operations dashboard with 6 user roles, 10 KPI cards, GT review workflow, AI evidence chain, hallucination risk review, Action Kanban, Content governance, and trends with attribution.

**Architecture:** Jinja2 SSR (server-rendered) + HTMX for partial updates. Page routes query data and render full HTML with ViewModel-prepared context. HTMX endpoints return HTML fragments for interactions (field accept, status transition, KPI expansion). JSON endpoints reserved for export/download only.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / PostgreSQL 16 / Jinja2 + HTMX 2.0 / Tailwind CDN / Chart.js 4.4 / Heroicons SVG inline / Fira Code + Fira Sans

**Design System:** Data-Dense Dashboard | Primary #1E40AF / Secondary #3B82F6 / CTA #F59E0B / Background #F8FAFC / Text #1E3A8A

**Reference Spec:** `docs/superpowers/specs/2026-05-29-phase12-dashboard-workbench-design.md`

**Review:** This v2 addresses all 13 P0 and 10 P1 findings from the architecture review dated 2026-05-29.

---

## Model Field Verification (P0-7)

Before any implementation, the following field names are confirmed against actual ORM models:

| Plan Reference | Real Model.Field | Status |
|---|---|---|
| `HallucinationResult.claim` | `HallucinationResult.ai_claim` | Use `ai_claim` |
| `HallucinationResult.error_type` | **DOES NOT EXIST** | Add `error_type` column via migration |
| `HallucinationResult.needs_human_review` | **DOES NOT EXIST** | Derive from `verdict == "uncertain"` and `severity == "P0"` |
| `QueryResult.ai_response` | `QueryResult.answer_text` | Use `answer_text` |
| `QueryResult.dimension` | **DOES NOT EXIST** | Join through `query_template_id` → `QueryTemplate.dimension` |
| `QueryResult.brand_mentioned` | **DOES NOT EXIST** | Detect from `answer_text` at query time, or add column |
| `QueryResult.cited_urls` | `QueryResult.citations` (JSONB) | Use `citations` |
| `MetricsSnapshot.sov_numerator` | **DOES NOT EXIST** | Read from `details.kpi_cards[].numerator` |
| `GroundTruthVersion.gt_coverage_rate` | EXISTS (Float, default=0.0) | OK |
| `ContentPackage.risk_level` | EXISTS (String(10)) | OK |
| `ContentPackage.publish_url` | EXISTS (Text) | OK |
| `ContentPackage.title` | **DOES NOT EXIST** | Use `content_items[0].title` or add column |
| `ActionTheme.priority` | EXISTS (String(10)) | OK |
| `ActionTheme.expected_kpi_impact` | EXISTS (JSONB) | OK |
| `FIELD_RISK_LEVELS` (field→risk) | **DOES NOT EXIST** | Derive from `GT_FIELD_LEVELS`: P0→high, P1→medium, P2→low |

### Stage 0 Migration (pre-requisite)

Before any template work, add missing columns:

```python
# In a new Alembic migration:
# 1. ALTER TABLE hallucination_results ADD COLUMN error_type VARCHAR(50) DEFAULT '';
# 2. ALTER TABLE query_results ADD COLUMN dimension VARCHAR(100) DEFAULT '';
# 3. ALTER TABLE query_results ADD COLUMN brand_mentioned BOOLEAN DEFAULT FALSE;
# 4. ALTER TABLE content_packages ADD COLUMN title VARCHAR(255) DEFAULT '';
```

---

## Route & API Architecture Specification (P0-3, P0-4, P0-12)

### Principle: SSR for pages, HTML fragments for HTMX, JSON for export only

```
Page Routes (return HTML):
  GET /                          → dashboard/index.html (redirect to first brand)
  GET /brands/{id}               → dashboard/index.html (with brand context)
  GET /brands/{id}/gt-review     → gt_review/index.html
  GET /brands/{id}/evidence      → evidence/index.html
  GET /brands/{id}/hallucinations→ hallucinations/index.html
  GET /brands/{id}/actions       → actions/index.html
  GET /brands/{id}/content       → content/index.html
  GET /brands/{id}/trends        → trends/index.html

HTMX Fragment Endpoints (return HTML partial):
  GET /api/brands/{id}/nav-links              → sidebar nav HTML (brand switch)
  GET /api/brands/{id}/kpi-card/{kpi_key}     → expanded KPI detail panel HTML
  POST /api/gt-candidates/{id}/fields/{field}  → updated field row HTML
  POST /api/action-themes/{id}/transition      → updated Kanban card HTML
  POST /api/hallucinations/{id}/review         → updated cluster HTML

JSON API Endpoints (for export/external):
  GET /api/brands/{id}/overview           → JSON (dashboard data)
  GET /api/brands/{id}/kpi-cards          → JSON (KPI detail)
  POST /api/content-packages/{id}/export  → JSON (export format)
  POST /api/dashboard/brands/{id}/reports/generate → JSON
```

### Auth Requirement (P0-4)

Every page route MUST include:
```python
user: User = Depends(get_current_user),
db: AsyncSession = Depends(get_db),
```

And verify `brand.organization_id == user.organization_id`.

Every state-changing POST MUST verify role permissions against the matrix.

### Permission Matrix

| Action | Viewer | Analyst | GT Reviewer | Content Editor | Legal Reviewer | Admin |
|--------|--------|---------|-------------|----------------|----------------|-------|
| View any page | Yes | Yes | Yes | Yes | Yes | Yes |
| Trigger collection | - | Yes | - | - | - | Yes |
| Review GT fields | - | - | Yes | - | - | Yes |
| Confirm/dismiss hallucinations | - | Yes | Yes | - | - | Yes |
| Generate content | - | - | - | Yes | - | Yes |
| Approve high-risk content | - | - | - | - | Yes | Yes |
| Mark published | - | - | - | Yes | - | Yes |
| Transition action status | - | Yes | Yes | Yes | - | Yes |

Permission helper:
```python
# src/api/deps.py
def require_role(user: User, *roles: str):
    """Raise 403 if user lacks any of the given roles."""
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
```

---

## ViewModel Layer (P0-6, P1-1)

All computation happens in ViewModels. Templates only render pre-computed values.

```
src/view_models/
  __init__.py
  dashboard.py      → build_dashboard_vm(brand, user, db)
  gt_review.py      → build_gt_review_vm(brand, user, db)
  evidence.py       → build_evidence_vm(brand, filters, user, db)
  hallucination.py  → build_hallucination_vm(brand, filters, user, db)
  action.py         → build_action_vm(brand, filters, user, db)
  content.py        → build_content_vm(brand, user, db)
  trends.py         → build_trends_vm(brand, range, user, db)
```

Each ViewModel returns a dict with pre-formatted display values:
```python
def build_dashboard_vm(brand, user, db) -> dict:
    """Returns: {kpi_cards: [{key, label, display_value, numerator, denominator,
                              confidence, confidence_label, trend_display,
                              trend_direction}], ...}"""
    # Get latest completed CollectionRun (P0-8 fix)
    latest_run = get_latest_completed_run(brand.id, db)
    snapshot = get_snapshot_for_run(latest_run.id, db) if latest_run else None

    kpi_cards = []
    for kpi_key in KPI_KEYS:
        card = build_kpi_card(kpi_key, snapshot, latest_run)
        kpi_cards.append(card)

    return {
        "brand": {"id": str(brand.id), "name": brand.name, "industry": brand.industry},
        "kpi_cards": kpi_cards,
        "health_score": compute_health_score(kpi_cards),
        "blocking_issues": build_blocking_issues(brand.id, db),
        "data_reliability": build_reliability_vm(latest_run, snapshot),
        "top_risks": build_top_risks(brand.id, db),
        "priority_actions": build_priority_actions(brand.id, db, limit=3),
        "recent_changes": build_recent_changes(brand.id, snapshot, db),
        "permissions": build_permissions_vm(user),
    }
```

---

## Component Partials (P1-3, P1-2)

Reusable UI components to avoid duplication across 7 pages:

```
src/templates/partials/components/
  kpi_card.html            ← single KPI card (clickable, expands)
  kpi_detail_panel.html    ← expanded KPI explanation
  status_badge.html        ← color-coded status pill
  risk_badge.html          ← high/medium/low risk indicator
  source_tier_badge.html   ← S/A/B/C/D tier badge
  priority_badge.html      ← P0/P1/P2 severity badge
  empty_state.html         ← "no data yet" with CTA
  error_state.html         ← "failed to load" with retry
  loading_skeleton.html    ← shimmer placeholder
  permission_denied.html   ← lock icon + message
  stale_data_banner.html   ← "data older than 7 days" warning
  partial_data_banner.html ← "X/Y platforms succeeded" warning
```

---

### Task 1: Stage 0 — Migration + Missing Fields

**Files:**
- Create: `alembic/versions/xxxx_phase12_prepare.py` (auto-generated name)
- Create: `src/view_models/__init__.py`
- Create: `src/view_models/dashboard.py` (ViewModel skeleton)
- Modify: `src/schemas/ground_truth.py` (add FIELD_TO_RISK_LEVEL helper)

- [ ] **Step 1: Generate and write migration**

```bash
cd /home/ffh/explore\ geo && python3 -m alembic revision --autogenerate -m "phase12_add_error_type_dimension_brand_mentioned_title"
# Review and trim to only the 4 needed columns:
# ALTER TABLE hallucination_results ADD COLUMN error_type VARCHAR(50) DEFAULT '';
# ALTER TABLE query_results ADD COLUMN dimension VARCHAR(100) DEFAULT '';
# ALTER TABLE query_results ADD COLUMN brand_mentioned BOOLEAN DEFAULT FALSE;
# ALTER TABLE content_packages ADD COLUMN title VARCHAR(255) DEFAULT '';
```

- [ ] **Step 2: Run migration**

```bash
python3 -m alembic upgrade head
```

- [ ] **Step 3: Add FIELD_TO_RISK_LEVEL helper to schemas/ground_truth.py**

```python
# Build reverse mapping: field_name → risk_level
def _build_field_risk_map():
    result = {}
    for field, level in GT_FIELD_LEVELS.items():
        if level == "P0":
            result[field] = "high"
        elif level == "P1":
            result[field] = "medium"
        else:
            result[field] = "low"
    return result

FIELD_TO_RISK_LEVEL = _build_field_risk_map()
```

- [ ] **Step 4: Create ViewModel directory with skeleton**

```python
# src/view_models/__init__.py
from src.view_models.dashboard import build_dashboard_vm
from src.view_models.gt_review import build_gt_review_vm
from src.view_models.evidence import build_evidence_vm
from src.view_models.hallucination import build_hallucination_vm
from src.view_models.action import build_action_vm
from src.view_models.content import build_content_vm
from src.view_models.trends import build_trends_vm
```

- [ ] **Step 5: Verify tests still pass**

```bash
python3 -m pytest tests/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add alembic/versions/ src/view_models/ src/schemas/ground_truth.py
git commit -m "feat: add phase12 migration (error_type, dimension, brand_mentioned, title) and ViewModel layer"
```

---

### Task 2: Base Template & Navigation (P0-1, P0-5)

**Files:**
- Rewrite: `src/templates/base.html`
- Rewrite: `src/static/css/app.css`

- [ ] **Step 1: Rewrite base.html with proper brand_id in nav links**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GEO Explorer — {% block title %}品牌AI可见度{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {
            colors: {
              primary: '#1E40AF', 'primary-light': '#3B82F6', cta: '#F59E0B',
              surface: '#F8FAFC', text: '#1E3A8A',
            },
            fontFamily: {
              heading: ['Fira Code', 'monospace'],
              body: ['Fira Sans', 'sans-serif'],
            },
          },
        },
      }
    </script>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link href="/static/css/app.css" rel="stylesheet">
</head>
<body class="bg-surface text-text font-body flex min-h-screen">
    {% set nav_items = [
        {"key": "dashboard", "label": "品牌总览", "icon": "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1h-2z", "href": "/brands/" ~ (current_brand_id or "")},
        {"key": "gt-review", "label": "GT 审核", "icon": "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z", "href": "/brands/" ~ (current_brand_id or "") ~ "/gt-review"},
        {"key": "evidence", "label": "AI 证据", "icon": "M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z", "href": "/brands/" ~ (current_brand_id or "") ~ "/evidence"},
        {"key": "hallucinations", "label": "幻觉风险", "icon": "M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z", "href": "/brands/" ~ (current_brand_id or "") ~ "/hallucinations"},
        {"key": "actions", "label": "Action 工作台", "icon": "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01", "href": "/brands/" ~ (current_brand_id or "") ~ "/actions"},
        {"key": "content", "label": "Content 管理", "icon": "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10", "href": "/brands/" ~ (current_brand_id or "") ~ "/content"},
        {"key": "trends", "label": "趋势归因", "icon": "M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z", "href": "/brands/" ~ (current_brand_id or "") ~ "/trends"},
    ] %}

    <nav id="sidebar" class="w-56 bg-primary text-white flex-shrink-0 min-h-screen hidden md:flex flex-col">
        <div class="px-5 py-5 border-b border-primary-light/30">
            <a href="/" class="font-heading text-lg font-bold tracking-tight">GEO Explorer</a>
        </div>

        <!-- Brand Selector -->
        <div class="px-4 py-3 border-b border-primary-light/20">
            {% if brands and current_brand_id %}
            <select class="w-full bg-primary-light/20 text-white text-sm rounded px-2 py-1.5 border border-primary-light/30
                           focus:outline-none focus:ring-1 focus:ring-cta cursor-pointer"
                    onchange="window.location.href = '/brands/' + this.value">
                {% for b in brands %}
                <option value="{{ b.id }}" class="text-gray-900" {% if b.id|string == current_brand_id %}selected{% endif %}>{{ b.name }}</option>
                {% endfor %}
            </select>
            {% else %}
            <p class="text-sm text-blue-200">暂无品牌</p>
            {% endif %}
        </div>

        <!-- Nav Items -->
        <ul class="flex-1 py-3 space-y-0.5">
            {% for item in nav_items %}
            <li>
                <a href="{% if current_brand_id %}{{ item.href }}{% else %}#{% endif %}"
                   class="flex items-center gap-3 px-5 py-2.5 text-sm text-blue-100 hover:bg-primary-light/20 hover:text-white transition-colors duration-200
                          {% if not current_brand_id %}opacity-50 pointer-events-none{% endif %}
                          {% if current_page == item.key %}bg-primary-light/30 text-white{% endif %}"
                   hx-boost="true">
                    <svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="{{ item.icon }}"/>
                    </svg>
                    {{ item.label }}
                </a>
            </li>
            {% endfor %}
        </ul>

        <div class="px-5 py-3 border-t border-primary-light/20 text-xs text-blue-200">
            <span>{{ current_brand_name or "GEO Explorer" }}</span>
            {% if collection_time %}
            <span class="block opacity-60">{{ collection_time[:10] }}</span>
            {% endif %}
        </div>
    </nav>

    <!-- Mobile hamburger -->
    <button class="md:hidden fixed top-3 left-3 z-50 p-2 rounded bg-primary text-white"
            onclick="document.getElementById('sidebar').classList.toggle('hidden'); document.getElementById('sidebar').classList.toggle('fixed'); document.getElementById('sidebar').classList.toggle('inset-y-0'); document.getElementById('sidebar').classList.toggle('z-40');">
        <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>
    </button>

    <main id="main-content" class="flex-1 overflow-auto">
        <div class="px-4 sm:px-6 lg:px-8 py-6 max-w-[1600px] mx-auto">
            {% block content %}{% endblock %}
        </div>
    </main>

    <div id="toast-container" class="fixed bottom-4 right-4 z-50 space-y-2"></div>

    <!-- HTMX global error handling (P1-4) -->
    <script>
    document.body.addEventListener('htmx:responseError', function(evt) {
        var toast = document.createElement('div');
        toast.className = 'bg-red-100 border border-red-300 text-red-800 px-4 py-2 rounded-lg shadow text-sm';
        toast.textContent = '操作失败 (' + evt.detail.xhr.status + ')，请重试';
        document.getElementById('toast-container').appendChild(toast);
        setTimeout(function() { toast.remove(); }, 5000);
    });
    document.body.addEventListener('htmx:sendError', function() {
        var toast = document.createElement('div');
        toast.className = 'bg-red-100 border border-red-300 text-red-800 px-4 py-2 rounded-lg shadow text-sm';
        toast.textContent = '网络错误，请检查连接';
        document.getElementById('toast-container').appendChild(toast);
        setTimeout(function() { toast.remove(); }, 5000);
    });
    // Chart.js lifecycle management (P1-5)
    window.geoCharts = {};
    document.body.addEventListener('htmx:beforeSwap', function(evt) {
        var container = evt.detail.target;
        container.querySelectorAll('canvas').forEach(function(c) {
            if (window.geoCharts[c.id]) { window.geoCharts[c.id].destroy(); delete window.geoCharts[c.id]; }
        });
    });
    </script>
</body>
</html>
```

- [ ] **Step 2: Rewrite app.css — NO @apply, plain CSS only (P0-5)**

```css
/* Skeleton loading animation */
@keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
.skeleton { background: linear-gradient(90deg, #e2e8f0 25%, #f1f5f9 50%, #e2e8f0 75%); background-size: 200% 100%; animation: shimmer 1.5s infinite; border-radius: 4px; }

/* Chart containers */
.chart-container { position: relative; width: 100%; }
.chart-container canvas { width: 100% !important; }

/* Status badges — plain CSS, no @apply */
.badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
.badge-p0 { background-color: #fee2e2; color: #b91c1c; }
.badge-p1 { background-color: #fef3c7; color: #b45309; }
.badge-p2 { background-color: #dbeafe; color: #1d4ed8; }
.badge-tier-S { background-color: #d1fae5; color: #065f46; }
.badge-tier-A { background-color: #ccfbf1; color: #0f766e; }
.badge-tier-B { background-color: #e0f2fe; color: #0369a1; }
.badge-tier-C { background-color: #f1f5f9; color: #475569; }
.badge-tier-D { background-color: #fef2f2; color: #9ca3af; }
.badge-success { background-color: #dcfce7; color: #166534; }
.badge-pending { background-color: #f1f5f9; color: #64748b; }
.badge-approved { background-color: #dbeafe; color: #1e40af; }
.badge-blocked { background-color: #fee2e2; color: #991b1b; }
.badge-verified { background-color: #d1fae5; color: #065f46; }

/* Risk level indicators */
.risk-high { border-left: 4px solid #ef4444; }
.risk-medium { border-left: 4px solid #f59e0b; }
.risk-low { border-left: 4px solid #22c55e; }

/* Kanban layout */
.kanban-column { min-height: 300px; }
.kanban-card { cursor: pointer; transition: box-shadow 200ms ease; }
.kanban-card:hover { box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }

/* htmx indicator */
.htmx-indicator { opacity: 0; transition: opacity 200ms ease-in; }
.htmx-request .htmx-indicator { opacity: 1; }

/* Focus rings for a11y */
*:focus-visible { outline: 2px solid #3B82F6; outline-offset: 2px; }

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

- [ ] **Step 3: Verify base renders**

```bash
curl -s http://localhost:8000/ | grep -c "GEO Explorer"
```

- [ ] **Step 4: Commit**

```bash
git add src/templates/base.html src/static/css/app.css
git commit -m "feat: rewrite base template with corrected nav links, auth context, and HTMX error handling"
```

---

### Task 3: Component Partials

**Files:**
- Create: `src/templates/partials/components/status_badge.html`
- Create: `src/templates/partials/components/risk_badge.html`
- Create: `src/templates/partials/components/priority_badge.html`
- Create: `src/templates/partials/components/source_tier_badge.html`
- Create: `src/templates/partials/components/kpi_card.html`
- Create: `src/templates/partials/components/empty_state.html`
- Create: `src/templates/partials/components/error_state.html`
- Create: `src/templates/partials/components/loading_skeleton.html`
- Create: `src/templates/partials/components/stale_data_banner.html`

- [ ] **Step 1: Create each component**

**status_badge.html:**
```html
{% macro status_badge(status, size='sm') %}
<span class="badge badge-{{ status }} {% if size == 'lg' %}text-sm px-3{% endif %}">{{ status }}</span>
{% endmacro %}
```

**priority_badge.html:**
```html
{% macro priority_badge(priority) %}
<span class="badge badge-{{ priority|lower }}">{{ priority }}</span>
{% endmacro %}
```

**source_tier_badge.html:**
```html
{% macro source_tier_badge(tier) %}
<span class="badge badge-tier-{{ tier }}" title="{{ TIER_LABELS.get(tier, tier) }}">{{ tier }}</span>
{% endmacro %}
```

**risk_badge.html:**
```html
{% macro risk_badge(level) %}
{% set colors = {'high': 'badge-p0', 'medium': 'badge-p1', 'low': 'badge-p2'} %}
<span class="badge {{ colors.get(level, 'badge-pending') }}">{{ level }}</span>
{% endmacro %}
```

**empty_state.html:**
```html
{% macro empty_state(title, message, action_url, action_label) %}
<div class="text-center py-16">
    <svg class="w-16 h-16 mx-auto text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/></svg>
    <h3 class="mt-4 text-lg font-semibold text-slate-600">{{ title }}</h3>
    <p class="mt-2 text-sm text-slate-500">{{ message }}</p>
    {% if action_url and action_label %}
    <a href="{{ action_url }}" class="inline-block mt-4 px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 cursor-pointer no-underline" hx-boost="true">{{ action_label }}</a>
    {% endif %}
</div>
{% endmacro %}
```

**kpi_card.html:**
```html
{% macro kpi_card(card) %}
<div class="bg-white rounded-xl p-4 shadow-sm border border-gray-100 cursor-pointer hover:shadow-md transition-shadow duration-200"
     hx-get="/api/brands/{{ card.brand_id }}/kpi-card/{{ card.key }}"
     hx-target="#kpi-detail-panel" hx-swap="innerHTML">
    <div class="text-xs text-slate-400 font-medium uppercase tracking-wide">{{ card.label }}</div>
    <div class="mt-1.5 font-heading text-2xl font-bold text-text">{{ card.display_value }}</div>
    {% if card.numerator is not none and card.denominator is not none %}
    <div class="text-xs text-slate-400 mt-1">{{ card.numerator }}/{{ card.denominator }}</div>
    {% endif %}
    {% if card.confidence_label %}
    <div class="mt-1.5">
        <span class="badge badge-{{ card.confidence_label }}">{{ card.confidence_label }}</span>
    </div>
    {% endif %}
    {% if card.trend_display %}
    <div class="mt-1 text-xs {% if card.trend_direction == 'up' %}text-green-600{% elif card.trend_direction == 'down' %}text-red-600{% else %}text-slate-400{% endif %}">
        {{ card.trend_display }}
    </div>
    {% endif %}
</div>
{% endmacro %}
```

- [ ] **Step 2: Commit**

```bash
git add src/templates/partials/components/
git commit -m "feat: add reusable UI component partials (badges, states, KPI card)"
```

---

### Task 4: Dashboard ViewModel + Page

**Files:**
- Create: `src/view_models/dashboard.py`
- Modify: `src/main.py` (add `/brands/{id}` route)
- Rewrite: `src/templates/dashboard/index.html`

- [ ] **Step 1: Implement build_dashboard_vm() (P0-8: use CollectionRun)**

```python
# src/view_models/dashboard.py
from sqlalchemy import select, desc, func
from src.models.collection_run import CollectionRun
from src.models.metrics_snapshot import MetricsSnapshot
from src.models.ground_truth import GroundTruthVersion
from src.models.gt_candidate import GroundTruthCandidate
from src.models.hallucination import HallucinationResult
from src.models.action_theme import ActionTheme
from src.models.content_package import ContentPackage
from src.schemas.ground_truth import KPI_DISPLAY_NAMES


KPI_KEYS = [
    "sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate",
    "scenario_recall", "semantic_stability", "differentiation",
    "cross_platform_consistency", "recommendation_quality",
]


async def get_latest_completed_run(brand_id, db):
    """Get the most recent run with completed analysis."""
    result = await db.execute(
        select(CollectionRun).where(
            CollectionRun.brand_id == brand_id,
            CollectionRun.analysis_status == "completed",
        ).order_by(desc(CollectionRun.analysis_completed_at)).limit(1)
    )
    return result.scalar_one_or_none()


async def build_dashboard_vm(brand, user, db) -> dict:
    latest_run = await get_latest_completed_run(brand.id, db)
    snapshot = None
    prev_snapshot = None

    if latest_run:
        snapshot_result = await db.execute(
            select(MetricsSnapshot).where(
                MetricsSnapshot.collection_run_id == latest_run.id,
                MetricsSnapshot.platform.is_(None),
                MetricsSnapshot.dimension.is_(None),
            ).limit(1)
        )
        snapshot = snapshot_result.scalar_one_or_none()

        # Previous run for trends
        prev_run_result = await db.execute(
            select(CollectionRun).where(
                CollectionRun.brand_id == brand.id,
                CollectionRun.analysis_status == "completed",
                CollectionRun.analysis_completed_at < latest_run.analysis_completed_at,
            ).order_by(desc(CollectionRun.analysis_completed_at)).limit(1)
        )
        prev_run = prev_run_result.scalar_one_or_none()
        if prev_run:
            prev_snap = await db.execute(
                select(MetricsSnapshot).where(
                    MetricsSnapshot.collection_run_id == prev_run.id,
                    MetricsSnapshot.platform.is_(None),
                    MetricsSnapshot.dimension.is_(None),
                ).limit(1)
            )
            prev_snapshot = prev_snap.scalar_one_or_none()

    # Build KPI cards with pre-computed display values
    kpi_cards = []
    if snapshot:
        ek = (snapshot.details or {}).get("extended_kpis", {})
        kpi_raw = {
            "sov": snapshot.sov,
            "first_rec_rate": snapshot.first_rec_rate,
            "accuracy_rate": snapshot.accuracy_rate,
            "completeness_rate": snapshot.completeness_rate,
            "citation_rate": snapshot.citation_rate,
            "scenario_recall": ek.get("scenario_recall", {}).get("value", 0) if isinstance(ek.get("scenario_recall"), dict) else 0,
            "semantic_stability": ek.get("semantic_stability", {}).get("value", 0) if isinstance(ek.get("semantic_stability"), dict) else 0,
            "differentiation": ek.get("differentiation", {}).get("value", 0) if isinstance(ek.get("differentiation"), dict) else 0,
            "cross_platform_consistency": ek.get("cross_platform_consistency", {}).get("value", 0) if isinstance(ek.get("cross_platform_consistency"), dict) else 0,
            "recommendation_quality": ek.get("recommendation_quality", {}).get("value", 0) if isinstance(ek.get("recommendation_quality"), dict) else 0,
        }

        kpi_cards_raw = (snapshot.details or {}).get("kpi_cards", [])

        for key in KPI_KEYS:
            raw = kpi_raw.get(key, 0)
            is_pct = key in ("sov", "first_rec_rate", "accuracy_rate", "completeness_rate", "citation_rate")
            if is_pct:
                display_value = f"{round(raw * 100)}%"
            else:
                display_value = f"{round(raw, 1)}"

            # Find numerator/denominator from kpi_cards
            card_detail = next((c for c in kpi_cards_raw if c.get("key") == key), {})
            numerator = card_detail.get("numerator")
            denominator = card_detail.get("denominator")
            confidence = card_detail.get("confidence", "medium")

            trend_display = None
            trend_direction = None
            if prev_snapshot and key in ("sov", "first_rec_rate", "accuracy_rate"):
                prev_val = getattr(prev_snapshot, key, 0)
                delta = raw - prev_val
                if abs(delta) > 0.001:
                    trend_display = f"{'+' if delta > 0 else ''}{round(delta * 100, 1)}%"
                    trend_direction = "up" if delta > 0 else "down"

            confidence_label = confidence  # "high" / "medium" / "low"

            kpi_cards.append({
                "key": key,
                "brand_id": str(brand.id),
                "label": KPI_DISPLAY_NAMES.get(key, key),
                "display_value": display_value,
                "numerator": numerator,
                "denominator": denominator,
                "confidence": confidence,
                "confidence_label": confidence_label,
                "trend_display": trend_display,
                "trend_direction": trend_direction,
            })

    # Health score: average of core accuracy KPIs
    health_score = 0
    if kpi_cards:
        core = [c for c in kpi_cards if c["key"] in ("accuracy_rate", "completeness_rate", "citation_rate")]
        if core:
            health_score = sum(
                float(c["display_value"].replace("%", "")) for c in core
            ) / len(core)

    # Blocking issues
    blocking_issues = []
    active_gt = await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand.id,
            GroundTruthVersion.status == "active",
        ).order_by(desc(GroundTruthVersion.version)).limit(1)
    )
    active_gt = active_gt.scalar_one_or_none()

    if not active_gt:
        blocking_issues.append({
            "type": "gt_missing",
            "message": "GT 未 Promote，无法正式计算准确率",
            "link": f"/brands/{brand.id}/gt-review",
        })

    p0_count = (await db.execute(
        select(func.count(HallucinationResult.id)).where(
            HallucinationResult.brand_id == brand.id,
            HallucinationResult.severity == "P0",
            HallucinationResult.human_reviewed == False,
        )
    )).scalar()
    if p0_count > 0:
        blocking_issues.append({
            "type": "p0_unreviewed",
            "message": f"P0 幻觉 ({p0_count}条) 未复核",
            "link": f"/brands/{brand.id}/hallucinations",
        })

    high_risk_pkgs = (await db.execute(
        select(func.count(ContentPackage.id)).where(
            ContentPackage.brand_id == brand.id,
            ContentPackage.risk_level == "high",
            ContentPackage.status == "needs_review",
        )
    )).scalar()
    if high_risk_pkgs > 0:
        blocking_issues.append({
            "type": "content_needs_review",
            "message": f"Content Package ({high_risk_pkgs}个) 高风险，需审核",
            "link": f"/brands/{brand.id}/content",
        })

    # Data reliability
    gt_coverage = active_gt.gt_coverage_rate if active_gt else 0
    pending_candidates = (await db.execute(
        select(func.count(GroundTruthCandidate.id)).where(
            GroundTruthCandidate.brand_id == brand.id,
            GroundTruthCandidate.status == "pending_review",
        )
    )).scalar()

    is_stale = False
    if latest_run and latest_run.analysis_completed_at:
        from datetime import datetime, timezone
        age_days = (datetime.now(timezone.utc) - latest_run.analysis_completed_at).days
        is_stale = age_days > 7

    is_partial = latest_run.failure_count > 0 if latest_run else False
    platform_success_rate = 0
    if latest_run and latest_run.total_queries > 0:
        platform_success_rate = latest_run.success_count / latest_run.total_queries

    data_reliability = {
        "active_gt": active_gt is not None,
        "gt_coverage": round(gt_coverage * 100),
        "pending_candidates": pending_candidates,
        "latest_snapshot_at": latest_run.analysis_completed_at.isoformat() if latest_run and latest_run.analysis_completed_at else None,
        "collection_run_id": str(latest_run.id) if latest_run else None,
        "is_stale": is_stale,
        "is_partial": is_partial,
        "platform_success_rate": round(platform_success_rate * 100),
    }

    # Priority action themes
    themes = (await db.execute(
        select(ActionTheme).where(
            ActionTheme.brand_id == brand.id,
            ActionTheme.status.in_(["detected", "confirmed"]),
        ).order_by(ActionTheme.priority.asc(), ActionTheme.created_at.desc()).limit(3)
    )).scalars().all()

    priority_actions = [{
        "id": str(t.id),
        "title": t.title,
        "priority": t.priority,
        "status": t.status,
        "affected_fields": t.affected_fields or [],
    } for t in themes]

    # Recent changes
    recent_changes = {}
    if prev_snapshot and snapshot:
        for key in ("sov", "first_rec_rate", "accuracy_rate"):
            delta = getattr(snapshot, key, 0) - getattr(prev_snapshot, key, 0)
            if abs(delta) > 0.001:
                recent_changes[key] = {
                    "delta": round(delta * 100, 1),
                    "direction": "up" if delta > 0 else "down",
                    "label": KPI_DISPLAY_NAMES.get(key, key),
                }

    return {
        "brand": {"id": str(brand.id), "name": brand.name, "industry": brand.industry or ""},
        "has_data": snapshot is not None,
        "kpi_cards": kpi_cards,
        "health_score": round(health_score),
        "health_label": "良好" if health_score >= 70 else ("一般" if health_score >= 40 else "需关注"),
        "blocking_issues": blocking_issues,
        "data_reliability": data_reliability,
        "top_risks": {
            "p0_hallucinations": p0_count,
            "p1_hallucinations": (await db.execute(
                select(func.count(HallucinationResult.id)).where(
                    HallucinationResult.brand_id == brand.id,
                    HallucinationResult.severity == "P1",
                    HallucinationResult.human_reviewed == False,
                )
            )).scalar(),
            "high_risk_content": high_risk_pkgs,
        },
        "priority_actions": priority_actions,
        "recent_changes": recent_changes,
        "permissions": {
            "can_trigger_collection": user.role in ("admin", "analyst"),
            "can_review_gt": user.role in ("admin", "gt_reviewer"),
            "can_confirm_hallucination": user.role in ("admin", "analyst", "gt_reviewer"),
            "can_generate_content": user.role in ("admin", "content_editor"),
            "can_approve_high_risk": user.role in ("admin", "legal_reviewer"),
        },
    }
```

- [ ] **Step 2: Add page route to main.py**

```python
@app.get("/brands/{brand_id}", response_class=HTMLResponse)
async def brand_dashboard(
    request: Request,
    brand_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_org_brand_or_404(brand_id, user, db)
    vm = await build_dashboard_vm(brand, user, db)

    # Also load brands list for sidebar
    org_brands = (await db.execute(
        select(Brand).where(Brand.organization_id == user.organization_id).order_by(Brand.name)
    )).scalars().all()

    return templates.TemplateResponse("dashboard/index.html", {
        "request": request,
        "vm": vm,
        "current_brand_id": str(brand.id),
        "current_brand_name": brand.name,
        "current_page": "dashboard",
        "brands": [{"id": str(b.id), "name": b.name} for b in org_brands],
        "collection_time": vm["data_reliability"]["latest_snapshot_at"],
        "KPI_DISPLAY_NAMES": KPI_DISPLAY_NAMES,
    })
```

- [ ] **Step 3: Rewrite dashboard/index.html using ViewModel + components**

```html
{% extends "base.html" %}
{% from "partials/components/kpi_card.html" import kpi_card %}
{% from "partials/components/empty_state.html" import empty_state %}
{% from "partials/components/stale_data_banner.html" import stale_data_banner %}
{% from "partials/components/priority_badge.html" import priority_badge %}

{% block title %}{{ vm.brand.name }} — 品牌总览{% endblock %}

{% block content %}
{% if not vm.has_data %}
{{ empty_state("暂无采集数据", "请先触发采集以获取品牌 AI 可见度数据", none, none) }}
{% if vm.permissions.can_trigger_collection %}
<div class="text-center mt-2">
    <button class="px-6 py-2 bg-primary text-white rounded-lg hover:bg-primary/90 cursor-pointer"
            hx-post="/api/dashboard/brands/{{ vm.brand.id }}/reports/generate" hx-swap="none">
        触发采集</button>
</div>
{% endif %}
{% else %}

<!-- Page Header -->
<div class="flex items-center justify-between mb-5">
    <div>
        <h1 class="font-heading text-2xl font-bold text-text">{{ vm.brand.name }}</h1>
        <p class="text-sm text-slate-500 mt-0.5">
            行业: {{ vm.brand.industry }}
            {% if vm.data_reliability.latest_snapshot_at %}
            <span class="ml-3">数据时间: {{ vm.data_reliability.latest_snapshot_at[:10] }}</span>
            {% endif %}
        </p>
    </div>
    <div class="flex gap-2">
        {% if vm.permissions.can_trigger_collection %}
        <button class="px-4 py-2 text-sm bg-primary text-white rounded-lg hover:bg-primary/90 transition-colors duration-200 cursor-pointer"
                hx-post="/api/dashboard/brands/{{ vm.brand.id }}/reports/generate" hx-swap="none">
            触发采集</button>
        {% endif %}
    </div>
</div>

<!-- Stale Data Warning -->
{% if vm.data_reliability.is_stale %}
<div class="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 mb-4 text-sm text-amber-700">
    数据已超过 7 天未更新，建议触发新一轮采集。
</div>
{% endif %}

<!-- Partial Data Warning -->
{% if vm.data_reliability.is_partial %}
<div class="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 mb-4 text-sm text-amber-700">
    本轮采集成功率 {{ vm.data_reliability.platform_success_rate }}%，KPI 置信度可能受影响。
</div>
{% endif %}

<!-- Blocking Issues -->
{% if vm.blocking_issues %}
<div class="mb-5 space-y-1.5">
    {% for issue in vm.blocking_issues %}
    <a href="{{ issue.link }}" class="flex items-center gap-2 px-4 py-2.5 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800 hover:bg-amber-100 transition-colors duration-200 no-underline cursor-pointer" hx-boost="true">
        <svg class="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-2.694-.833-3.464 0L3.34 16c-.77.833.192 2.5 1.732 2.5z"/></svg>
        {{ issue.message }} →
    </a>
    {% endfor %}
</div>
{% endif %}

<!-- Health Score + Data Reliability -->
<div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">AI 认知健康分</h3>
        <div class="flex items-center gap-4">
            <div class="relative w-20 h-20">
                <canvas id="health-ring" width="80" height="80"></canvas>
                <div class="absolute inset-0 flex items-center justify-center">
                    <span class="font-heading text-lg font-bold text-text">{{ vm.health_score }}</span>
                </div>
            </div>
            <div>
                <p class="text-sm font-medium text-text">{{ vm.health_label }}</p>
            </div>
        </div>
    </div>
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100 lg:col-span-2">
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">数据可信度</h3>
        <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 text-center">
            <div><div class="text-lg font-bold text-text">{{ '激活' if vm.data_reliability.active_gt else '缺失' }}</div><div class="text-xs text-slate-500">GT 状态</div></div>
            <div><div class="text-lg font-bold text-text">{{ vm.data_reliability.gt_coverage }}%</div><div class="text-xs text-slate-500">GT 覆盖率</div></div>
            <div><div class="text-lg font-bold {% if vm.data_reliability.pending_candidates > 0 %}text-amber-600{% else %}text-text{% endif %}">{{ vm.data_reliability.pending_candidates }}</div><div class="text-xs text-slate-500">待审核</div></div>
            <div><div class="text-lg font-bold text-text">{{ vm.data_reliability.platform_success_rate }}%</div><div class="text-xs text-slate-500">采集成功率</div></div>
            <div><div class="text-lg font-bold text-text">{{ vm.data_reliability.latest_snapshot_at[:10] if vm.data_reliability.latest_snapshot_at else 'N/A' }}</div><div class="text-xs text-slate-500">最新快照</div></div>
        </div>
    </div>
</div>

<!-- 10 KPI Cards -->
<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
    {% for card in vm.kpi_cards %}
    {{ kpi_card(card) }}
    {% endfor %}
</div>
<div id="kpi-detail-panel" class="mb-4"></div>

<!-- Top Risks + Priority Actions -->
<div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">当前最大风险</h3>
        <div class="flex gap-3">
            <div class="flex-1 bg-red-50 rounded-lg p-3 text-center">
                <div class="text-2xl font-bold text-red-700">{{ vm.top_risks.p0_hallucinations }}</div>
                <div class="text-xs text-red-600 mt-0.5">P0 幻觉</div>
            </div>
            <div class="flex-1 bg-amber-50 rounded-lg p-3 text-center">
                <div class="text-2xl font-bold text-amber-700">{{ vm.top_risks.p1_hallucinations }}</div>
                <div class="text-xs text-amber-600 mt-0.5">P1 幻觉</div>
            </div>
            <div class="flex-1 bg-red-50 rounded-lg p-3 text-center">
                <div class="text-2xl font-bold text-red-700">{{ vm.top_risks.high_risk_content }}</div>
                <div class="text-xs text-red-600 mt-0.5">高风险内容</div>
            </div>
        </div>
    </div>
    <div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
        <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">最优先行动</h3>
        {% if vm.priority_actions %}
        <div class="space-y-2">
            {% for theme in vm.priority_actions %}
            <a href="/brands/{{ vm.brand.id }}/actions" class="block px-4 py-3 rounded-lg border border-gray-200 hover:shadow-sm transition-shadow duration-200 cursor-pointer no-underline" hx-boost="true">
                <div class="flex items-center justify-between">
                    <span class="text-sm font-medium text-text">{{ theme.title }}</span>
                    {{ priority_badge(theme.priority) }}
                </div>
            </a>
            {% endfor %}
        </div>
        {% else %}
        <p class="text-sm text-slate-400">暂无待处理的 Action Theme</p>
        {% endif %}
    </div>
</div>

<!-- Recent Changes -->
{% if vm.recent_changes %}
<div class="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
    <h3 class="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">最近变化 (vs 上轮)</h3>
    <div class="flex gap-4 text-sm">
        {% for key, change in vm.recent_changes.items() %}
        <span>{{ change.label }}: <strong class="{% if change.direction == 'up' %}text-green-600{% else %}text-red-600{% endif %}">{{ '+' if change.direction == 'up' else '' }}{{ change.delta }}%</strong></span>
        {% endfor %}
    </div>
</div>
{% endif %}

{% endif %}
{% endblock %}

{% block scripts %}
<script>
(function() {
    var canvas = document.getElementById('health-ring');
    if (!canvas) return;
    var score = {{ vm.health_score }};
    var color = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
    window.geoCharts['health-ring'] = new Chart(canvas, {
        type: 'doughnut',
        data: { datasets: [{ data: [score, 100 - score], backgroundColor: [color, '#e2e8f0'], borderWidth: 0, circumference: 270, rotation: 225 }] },
        options: { cutout: '75%', responsive: false, plugins: { legend: { display: false }, tooltip: { enabled: false } } },
    });
})();
</script>
{% endblock %}
```

- [ ] **Step 4: Commit**

```bash
git add src/view_models/dashboard.py src/main.py src/templates/dashboard/index.html
git commit -m "feat: implement dashboard page with ViewModel, CollectionRun-based lookup, and component partials"
```

---

### Task 5: GT Review Page (P0-9: batch evidence loading)

**Files:**
- Create: `src/view_models/gt_review.py`
- Create: `src/templates/gt_review/index.html`
- Modify: `src/main.py` (add route)

- [ ] **Step 1: Implement build_gt_review_vm() with batched evidence queries**

```python
# src/view_models/gt_review.py
from collections import defaultdict
from sqlalchemy import select
from src.models.gt_candidate import GroundTruthCandidate
from src.models.gt_evidence import GroundTruthEvidence
from src.models.ground_truth import GroundTruthVersion
from src.schemas.ground_truth import FIELD_TO_RISK_LEVEL, SOURCE_TIERS, FIELD_EVIDENCE_REQUIREMENTS, HIGH_RISK_FIELD_TIER_REQUIREMENTS


async def build_gt_review_vm(brand, user, db) -> dict:
    # Get latest candidate
    candidate = (await db.execute(
        select(GroundTruthCandidate).where(
            GroundTruthCandidate.brand_id == brand.id,
            GroundTruthCandidate.status == "pending_review",
        ).order_by(GroundTruthCandidate.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    # Batch load ALL evidence for this candidate (P0-9 fix)
    evidences_by_field = defaultdict(list)
    promote_blocked = []
    if candidate:
        evidence_rows = (await db.execute(
            select(GroundTruthEvidence).where(
                GroundTruthEvidence.candidate_id == candidate.id,
            )
        )).scalars().all()
        for ev in evidence_rows:
            evidences_by_field[ev.field_name].append(ev)

        # Promote readiness check
        for field, req in HIGH_RISK_FIELD_TIER_REQUIREMENTS.items():
            if field not in candidate.candidate_json:
                continue
            field_ev = evidences_by_field.get(field, [])
            req_score = SOURCE_TIERS.get(req, {}).get("score", 0.4)
            sufficient = [e for e in field_ev
                          if SOURCE_TIERS.get(e.source_tier, {}).get("score", 0) >= req_score]
            if not sufficient:
                promote_blocked.append({
                    "field": field,
                    "reason": f"需要 {req}-级证据（当前最佳: {max((e.source_tier for e in field_ev), default='无')}）",
                })

    # Active GT
    active_gt = (await db.execute(
        select(GroundTruthVersion).where(
            GroundTruthVersion.brand_id == brand.id,
            GroundTruthVersion.status == "active",
        ).order_by(GroundTruthVersion.version.desc()).limit(1)
    )).scalar_one_or_none()

    # Build field list
    fields = []
    if candidate:
        for fname, fval in (candidate.candidate_json or {}).items():
            risk = FIELD_TO_RISK_LEVEL.get(fname, "low")
            field_ev = evidences_by_field.get(fname, [])
            # Determine status
            if any(ev.review_status == "flagged" for ev in field_ev):
                status = "flagged"
            elif any(ev.human_confirmed for ev in field_ev):
                status = "accepted"
            else:
                status = "pending"

            # Detect conflicts
            tiers = [ev.source_tier for ev in field_ev if ev.source_tier in ("S", "A")]
            has_conflict = len(set(ev.value for ev in field_ev)) > 1

            fields.append({
                "name": fname,
                "value": str(fval)[:200],
                "risk_level": risk,
                "status": status,
                "has_conflict": has_conflict,
                "evidence_count": len(field_ev),
                "evidences": [{
                    "source_tier": ev.source_tier,
                    "source_name": ev.source_name,
                    "source_url": ev.source_url,
                    "excerpt": (ev.excerpt or "")[:200],
                    "value": ev.value,
                    "human_confirmed": ev.human_confirmed,
                } for ev in field_ev],
            })

    # Progress stats
    total = len(fields)
    reviewed = sum(1 for f in fields if f["status"] in ("accepted",))
    high_risk_total = sum(1 for f in fields if f["risk_level"] == "high")
    high_risk_reviewed = sum(1 for f in fields if f["risk_level"] == "high" and f["status"] in ("accepted",))
    uncertain = sum(1 for f in fields if f["status"] == "flagged")
    conflicts = sum(1 for f in fields if f["has_conflict"])

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "has_candidate": candidate is not None,
        "candidate_id": str(candidate.id) if candidate else None,
        "progress": {
            "total": total, "reviewed": reviewed,
            "high_risk_total": high_risk_total, "high_risk_reviewed": high_risk_reviewed,
            "uncertain": uncertain, "conflicts": conflicts,
        },
        "fields": fields,
        "active_gt": active_gt.ground_truth_json if active_gt else None,
        "can_promote": len(promote_blocked) == 0 and total > 0,
        "promote_blocked": promote_blocked,
        "permissions": {
            "can_review": user.role in ("admin", "gt_reviewer"),
            "can_promote": user.role in ("admin", "gt_reviewer"),
        },
    }
```

- [ ] **Step 2: Add page route**

```python
@app.get("/brands/{brand_id}/gt-review", response_class=HTMLResponse)
async def gt_review_page(
    request: Request,
    brand_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    brand = await get_org_brand_or_404(brand_id, user, db)
    vm = await build_gt_review_vm(brand, user, db)
    org_brands = await _get_org_brands(user, db)
    return templates.TemplateResponse("gt_review/index.html", {
        "request": request, "vm": vm,
        "current_brand_id": str(brand.id), "current_brand_name": brand.name,
        "current_page": "gt-review", "brands": org_brands,
    })
```

- [ ] **Step 3: Create gt_review/index.html template**

Template renders:
- Progress bar: reviewed/total, high-risk complete, uncertain, conflicts
- Filter tabs: All | Conflicts | High Risk | Unreviewed
- Field list: each row shows name, value (truncated), risk badge, status badge, conflict indicator
- Click row to expand: evidence list with source_tier badges, URLs, excerpts
- Action buttons per field (if `vm.permissions.can_review`): Accept / Edit / Delete / Flag Uncertain
- Batch accept button for low-risk fields
- Promote button with blocking reasons tooltip

- [ ] **Step 4: Commit**

```bash
git add src/view_models/gt_review.py src/main.py src/templates/gt_review/
git commit -m "feat: implement GT review page with batched evidence loading and promote readiness check"
```

---

### Task 6: AI Evidence Page

**Files:**
- Create: `src/view_models/evidence.py`
- Create: `src/templates/evidence/index.html`
- Modify: `src/main.py` (add route)

- [ ] **Step 1: Implement build_evidence_vm()**

Query `QueryResult` joined with `HallucinationResult`, using real field names (`answer_text`, `citations`, `collected_at`). Support filters: platform, dimension, brand_mentioned, has_p0, collection_run_id.

- [ ] **Step 2: Add page route + create template**

Evidence cards showing question → AI answer (with brand mentions highlighted) → citations → GT comparison → linked hallucinations → KPI contributions.

- [ ] **Step 3: Commit**

```bash
git add src/view_models/evidence.py src/main.py src/templates/evidence/
git commit -m "feat: implement AI evidence page with KPI/hallucination/GT linkage"
```

---

### Task 7: Hallucination Risk Page (P0-10: proper cluster key)

**Files:**
- Create: `src/view_models/hallucination.py`
- Create: `src/templates/hallucinations/index.html`
- Modify: `src/main.py` (add route)

- [ ] **Step 1: Implement proper clustering (P0-10 fix)**

```python
# Cluster key: (error_type, severity, field_name, query_dimension)
def _cluster_key(h: HallucinationResult, dimension: str) -> tuple:
    return (h.error_type or "unknown", h.severity, h.field_name, dimension or "")

# Build clusters with: typical_ai_claims, affected_platforms, gt_value, kpi_impact
```

- [ ] **Step 2: Add page route + template**

View toggle: Cluster ↔ Detail list. Each cluster card shows: error_type, severity, field, dimension, count, platforms, typical AI claims, GT correct value. Per-item review: Confirm / Dismiss / "GT is wrong" / "Low risk variation."

- [ ] **Step 3: Commit**

```bash
git add src/view_models/hallucination.py src/main.py src/templates/hallucinations/
git commit -m "feat: implement hallucination risk page with proper multi-field clustering"
```

---

### Task 8: Action Workbench Page (P0-11: permission guards)

**Files:**
- Create: `src/view_models/action.py`
- Create: `src/templates/actions/index.html`
- Modify: `src/main.py` (add route)
- Modify: `src/api/actions.py` (add transition endpoint with guards)

- [ ] **Step 1: Implement state transition with permissions (P0-11 fix)**

```python
# TRANSITION_GUARDS: who can trigger each transition
TRANSITION_GUARDS = {
    ("detected", "confirmed"): ("admin", "analyst", "gt_reviewer"),
    ("confirmed", "content_generating"): ("admin", "content_editor"),
    ("content_ready", "needs_review"): ("admin", "content_editor"),
    ("needs_review", "approved"): ("admin", "legal_reviewer"),
    ("approved", "published_marked"): ("admin", "content_editor"),
    ("published_marked", "verification_pending"): ("admin",),
    ("verification_pending", "verified"): ("admin", "analyst"),
}

def can_transition(user_role: str, from_status: str, to_status: str) -> bool:
    allowed_roles = TRANSITION_GUARDS.get((from_status, to_status), ())
    return user_role in allowed_roles
```

- [ ] **Step 2: Add page route + Kanban template**

Kanban columns per status. Each card: priority badge, title, affected fields, platforms, KPI impact, effort level. Filter by priority, status. HTMX transition buttons with permission gating.

- [ ] **Step 3: Commit**

```bash
git add src/view_models/action.py src/main.py src/templates/actions/ src/api/actions.py
git commit -m "feat: implement Action workbench with role-gated state transitions"
```

---

### Task 9: Content Management Page (P0-12: backend APIs)

**Files:**
- Create: `src/view_models/content.py`
- Create: `src/templates/content/index.html`
- Modify: `src/main.py` (add route)
- Modify: `src/api/actions.py` (add content-package management endpoints)

- [ ] **Step 1: Add content management API endpoints (P0-12 fix)**

```python
@router.get("/api/brands/{brand_id}/content-packages")
async def list_content_packages(...):
    """List with filters: risk_level, status. Returns paginated results."""

@router.post("/api/content-packages/{package_id}/approve")
async def approve_content_package(...):
    """Legal Reviewer or Admin only. Sets status to approved."""

@router.post("/api/content-packages/{package_id}/reject")
async def reject_content_package(...):
    """Return to draft with rejection reason."""
    body: {"reason": str}

@router.post("/api/content-packages/{package_id}/mark-published")
async def mark_content_published(...):
    """Content Editor or Admin. Requires publish_url in body."""
    body: {"publish_url": str}

@router.get("/api/content-packages/{package_id}/fact-check")
async def get_fact_check_detail(...):
    """Return sentence-level fact mapping for review."""
```

- [ ] **Step 2: Add page route + template**

Content list with risk badges, fact source mapping (expandable), publishing checklist, export buttons. High-risk content requires approval.

- [ ] **Step 3: Commit**

```bash
git add src/view_models/content.py src/main.py src/templates/content/ src/api/actions.py
git commit -m "feat: implement content management page with approve/reject/publish APIs"
```

---

### Task 10: Trends & Attribution Page (P0-13: real logic)

**Files:**
- Create: `src/view_models/trends.py`
- Create: `src/templates/trends/index.html`
- Modify: `src/main.py` (add route)

- [ ] **Step 1: Implement minimal working attribution (P0-13 fix)**

```python
def compute_attribution_label(pre_val, post_val, sample_size, gt_changed, platform_failure) -> str:
    if sample_size < 3:
        return "样本不足"
    if platform_failure:
        return "平台失败影响"
    if gt_changed:
        return "GT 更新混淆"
    if abs(post_val - pre_val) > 0.05:
        return "可能由 Action 导致"
    return "无明显效果"

def get_pre_post_kpi(action_theme, db) -> dict:
    """Get pre/post publish KPI values."""
    # Find publish time from related content packages
    # Get snapshots before/after publish
    # Return pre_avg, post_avg, change, sample_size, attribution_label
```

- [ ] **Step 2: Add page route + template**

Line charts (Chart.js) for 5 core KPIs with event markers. Time range: week/month/quarter. Action effect verification table with attribution labels.

- [ ] **Step 3: Commit**

```bash
git add src/view_models/trends.py src/main.py src/templates/trends/
git commit -m "feat: implement trends page with minimal working attribution logic"
```

---

### Task 11: Responsive Polish & State Coverage

**Files:**
- Modify: All template files (responsive + state handling)

- [ ] **Step 1: Verify responsive breakpoints**

- 375px: sidebar hidden (mobile hamburger), KPI 1 column, tables → stacked cards
- 768px: sidebar collapsible, KPI 2 columns
- 1024px: sidebar fixed, KPI 3-4 columns
- 1440px: KPI 5 columns, data-dense

- [ ] **Step 2: Verify 8 states on every page**

- `loading`: skeleton shimmer shown during HTMX requests
- `empty`: empty_state component with CTA
- `error`: error_state component with retry
- `permission_denied`: permission_denied component
- `partial_data`: partial_data_banner shown when `is_partial`
- `stale_data`: stale_data_banner shown when `is_stale`
- `success`: normal content

- [ ] **Step 3: Accessibility audit**

- [ ] All form inputs have `<label>`
- [ ] All icon-only buttons have `aria-label`
- [ ] Color never the only status indicator (text labels always present)
- [ ] Tab order logical
- [ ] Focus rings visible
- [ ] `prefers-reduced-motion` respected

- [ ] **Step 4: Commit**

```bash
git add src/templates/ src/static/css/app.css
git commit -m "feat: add responsive design, 8-state coverage, and accessibility refinements"
```

---

### Task 12: Integration Tests

**Files:**
- Create: `tests/test_dashboard_pages.py`
- Create: `tests/test_dashboard_viewmodels.py`

- [ ] **Step 1: Write ViewModel tests**

```python
# tests/test_dashboard_viewmodels.py
class TestDashboardViewModel:
    async def test_build_dashboard_vm_no_data(self, db_session, test_brand, test_user):
        """Dashboard VM with no collection run returns has_data=False."""
        vm = await build_dashboard_vm(test_brand, test_user, db_session)
        assert vm["has_data"] is False

    async def test_build_dashboard_vm_with_data(self, db_session, test_brand, test_user, test_collection_run):
        """Dashboard VM with completed run returns KPI cards."""
        vm = await build_dashboard_vm(test_brand, test_user, db_session)
        assert vm["has_data"] is True
        assert len(vm["kpi_cards"]) == 10
        assert "display_value" in vm["kpi_cards"][0]

    async def test_blocking_issues_no_gt(self, db_session, test_brand, test_user):
        """No active GT → blocking issue."""
        vm = await build_dashboard_vm(test_brand, test_user, db_session)
        assert any(i["type"] == "gt_missing" for i in vm["blocking_issues"])

    async def test_health_score_range(self, db_session, test_brand, test_user, test_collection_run):
        """Health score between 0-100."""
        vm = await build_dashboard_vm(test_brand, test_user, db_session)
        assert 0 <= vm["health_score"] <= 100


class TestGTReviewViewModel:
    async def test_no_n_plus_one_queries(self, db_session, test_brand, test_user, test_gt_candidate_with_evidence):
        """GT review loads evidence in one batch query, not N+1."""
        # Verify by checking query count
        ...

    async def test_promote_blocked_insufficient_evidence(self, ...):
        """High-risk fields without S/A tier evidence block promote."""
        ...

    async def test_field_risk_from_gt_field_levels(self, ...):
        """P0 fields → high risk, P1 → medium, P2 → low."""
        ...


class TestHallucinationClustering:
    async def test_cluster_key_includes_field_and_dimension(self, ...):
        """P0-10: Cluster key uses (error_type, severity, field_name, dimension)."""
        ...


class TestActionTransitions:
    async def test_viewer_cannot_transition(self, ...):
        """P0-11: Viewer role cannot transition action status."""
        ...

    async def test_content_editor_cannot_approve_high_risk(self, ...):
        """P0-11: Content editor cannot approve → Legal Reviewer only."""
        ...


class TestAttribution:
    async def test_insufficient_sample_label(self, ...):
        """P0-13: Sample < 3 returns '样本不足'."""
        ...

    async def test_possible_action_effect_label(self, ...):
        """P0-13: Significant change → '可能由 Action 导致'."""
        ...
```

- [ ] **Step 2: Write page rendering tests**

```python
class TestPageRoutes:
    async def test_all_pages_require_auth(self, client):
        """All 7 page routes return 401 without token."""
        for path in ["/brands/test-id/gt-review", "/brands/test-id/evidence",
                      "/brands/test-id/hallucinations", "/brands/test-id/actions",
                      "/brands/test-id/content", "/brands/test-id/trends"]:
            resp = await client.get(path)
            assert resp.status_code == 401

    async def test_cross_org_brand_rejected(self, client, auth_headers, other_org_brand):
        """P0-4: Cannot access brand from another organization."""
        resp = await client.get(f"/brands/{other_org_brand.id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_dashboard_page_renders_200(self, client, auth_headers, test_brand):
        resp = await client.get(f"/brands/{test_brand.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert "GEO Explorer" in resp.text

    async def test_gt_review_page_renders_200(self, client, auth_headers, test_brand):
        resp = await client.get(f"/brands/{test_brand.id}/gt-review", headers=auth_headers)
        assert resp.status_code == 200

    async def test_nav_links_contain_real_brand_id(self, client, auth_headers, test_brand):
        """P0-1: Nav links use real brand_id, not '{id}' placeholder."""
        resp = await client.get(f"/brands/{test_brand.id}", headers=auth_headers)
        assert f"/brands/{test_brand.id}/gt-review" in resp.text
        assert "/brands/{id}/" not in resp.text
```

- [ ] **Step 3: Run all tests**

```bash
python3 -m pytest tests/ -v
# Existing 89 tests must continue passing
```

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add ViewModel unit tests, page route tests, and permission tests"
```

---

## Verification Checklist

- [ ] `python3 -m pytest tests/ -v` — 89+ tests, 0 failures
- [ ] `curl -s http://localhost:8000/health` — `{"status":"ok"}`
- [ ] Browser: 7 pages render at 375/768/1024/1440
- [ ] Browser: Brand selector switches pages correctly
- [ ] Browser: Navigation links use real brand_id (never `{id}`)
- [ ] Browser: KPI cards expand on click (HTMX fragment)
- [ ] Browser: GT review field accept/edit via HTMX
- [ ] Browser: Hallucination cluster review workflow
- [ ] Browser: Action transition guarded by role
- [ ] Browser: Content approve requires Legal Reviewer for high-risk
- [ ] Browser: Trend charts render with Chart.js
- [ ] No `@apply` in CSS
- [ ] No `{id}` or `{value}` placeholders in HTML
- [ ] No emoji icons (Heroicons SVG only)
- [ ] Focus rings visible on Tab navigation
- [ ] Color contrast 4.5:1 on all text
- [ ] All page routes require auth
- [ ] N+1 queries avoided (batch evidence loading)
