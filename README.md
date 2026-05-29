# GEO Explorer — Brand AI Visibility Monitoring & Optimization

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/fastapi-0.136-green.svg)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/tests-112%20passed-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A **Brand AI Visibility Monitoring & Optimization Platform** (GEO — Generative Engine Optimization). Systematically queries multiple AI platforms (DeepSeek, Kimi, Doubao) to monitor how AI describes your brand, detects hallucinations against verified Ground Truth, generates corrective content packages, and verifies improvements — forming a closed optimization loop.

> **One sentence:** Make your brand correct, complete, and competitive in the eyes of AI.

---

## Table of Contents

- [What It Does](#what-it-does)
- [10 KPI Metrics](#10-kpi-metrics)
- [Complete Pipeline](#complete-pipeline)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [7-Page Operations Dashboard](#7-page-operations-dashboard)
- [API Overview](#api-overview)
- [Architecture Decisions](#architecture-decisions)
- [Current Status](#current-status)
- [Team Collaboration](#team-collaboration)
- [License](#license)

---

## What It Does

1. **Auto-collects Ground Truth** — Input a brand name, the system queries AI platforms + search engines to auto-build a structured fact database with S/A/B/C/D source tier ratings
2. **Human Review & Promote** — Field-level GT review with evidence chains, conflict detection, and promote readiness checks
3. **Systematic AI Monitoring** — 22 query templates × 5 dimensions × 3 AI platforms = 66 systematic brand queries
4. **10 KPI Analysis** — Each KPI includes numerator, denominator, confidence, and explainable detail cards
5. **Semantic Hallucination Detection** — 9 error types with human review workflow
6. **Action Theme Aggregation** — Clusters raw detections into max 10 high-priority themes
7. **Content Package Generation** — LLM-generated correctable content with fact-checking + Schema.org JSON-LD
8. **Report Delivery** — .md / .docx / .pdf diagnostic reports with content assets
9. **Trend Attribution** — Pre/post-publish KPI comparison with 6-type attribution labeling

---

## 10 KPI Metrics

| KPI | Description | Has Detail Card |
|-----|-------------|:---:|
| SOV (Share of Voice) | How often the brand is mentioned in AI responses | ✓ |
| First Recommendation Rate | How often the brand is recommended first | ✓ |
| Accuracy | How accurately AI describes the brand vs GT | ✓ |
| Completeness | How many key GT fields AI covers | ✓ |
| Citation Rate | How often AI cites official sources | ✓ |
| Scenario Recall | Brand recall in non-branded scenario queries | ✓ |
| Semantic Stability | Consistency of brand descriptions across platforms | ✓ |
| Differentiation | Appearance rate of unique selling points | ✓ |
| Cross-Platform Consistency | Stability of key brand claims across platforms | ✓ |
| Recommendation Quality | Substantive quality of AI recommendation reasons | ✓ |

Every KPI returns: `numerator` / `denominator` / `confidence` + expandable explanation card.

---

## Complete Pipeline

```
GT Auto-Collection (S/A/B/C/D tiers)
  → GT Human Review (field-level evidence + promote)
    → Brand GEO Collection (66 AI calls × 3 platforms)
      → 10 KPI Analysis (numerator/denominator/confidence)
        → Semantic Hallucination Detection (9 error types)
          → Action Theme Aggregation (max 10 themes)
            → Content Package Generation (risk-graded)
              → Report Delivery (.md/.docx/.pdf)
                → Trend & Attribution Verification
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 (full async) |
| Web Framework | FastAPI + Jinja2 SSR + HTMX 2.0 |
| ORM | SQLAlchemy 2.0 async + Alembic |
| Database | PostgreSQL 16 (JSONB support) |
| Task Queue | Celery + Redis 7 |
| Frontend | Tailwind CDN + Chart.js 4.4 + Heroicons SVG |
| Fonts | Fira Code (headings) + Fira Sans (body) |
| AI Platforms | DeepSeek / Kimi / Doubao (OpenAI-compatible) |
| Search | DuckDuckGo + Google Custom Search (reserved) |
| PDF | Puppeteer + marked (Chrome headless rendering) |
| Word | python-docx |
| Auth | JWT (Cookie + Bearer dual channel) |
| Deploy | Systemd daemons (geo-redis / geo-celery / geo-api) |

---

## Project Structure

```
explore geo/
├── src/
│   ├── models/         # 22 ORM data models
│   ├── adapters/       # AI platform adapters (DeepSeek/Kimi/Doubao/Wenxin)
│   ├── collector/      # Collection engine + GT auto-collector
│   ├── analyzer/       # 10 KPI calculators + hallucination detector + aggregator
│   ├── actions/        # Action engine + content packages + fact checker + schema generator
│   ├── api/            # REST API endpoints (auth/brands/metrics/dashboard/GT/hallucinations/actions)
│   ├── search/         # DuckDuckGo + AI search backends
│   ├── reports/        # Report generation + PDF/DOCX export
│   ├── schemas/        # GT field definitions + source tier system + KPI names
│   ├── view_models/    # ViewModel layer (pre-compute display values, templates render only)
│   └── templates/      # 21 Jinja2 templates (7 pages + 11 components + base layout)
├── tests/              # 112 tests, 0 failures
├── alembic/            # 10+ database migrations
├── deploy/             # systemd service files
├── docs/superpowers/   # Design specs + implementation plans
├── reports/            # Brand diagnostic report output (gitignored)
├── requirements.txt    # Python dependencies
├── setup.sh            # One-click init script
├── SYNC_GUIDE.md       # Team collaboration guide
└── CLAUDE.md           # Project instructions for Claude Code
```

**Stats:** 92 Python files · 21 template files · 112 tests (0 failures) · 70+ commits · 22 database tables

---

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16
- Redis 7
- Node.js 22+ (for PDF generation)

### One-Click Setup

```bash
git clone <repo-url> geo-explorer
cd geo-explorer
bash setup.sh
```

This automatically: creates virtualenv → installs dependencies → creates .env from template → runs database migrations.

### Manual Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
alembic upgrade head
```

### Start

```bash
# API server
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# With Celery workers (for async collection tasks)
celery -A src.celery_app worker --loglevel=info --concurrency=4 &

# Or via systemd (production)
sudo systemctl start geo-redis geo-celery geo-api
```

Open `http://localhost:8000/login` in browser — click one-click dev login to enter dashboard.

### API Quick Test

```bash
# Register
curl -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test","email":"test@test.com","password":"test123","org_name":"My Org"}'

# Create brand
curl -X POST http://localhost:8000/api/brands \
  -H 'Authorization: Bearer <token>' \
  -d '{"name":"Your Brand","industry":"Technology"}'

# Trigger GT collection (async)
curl -X POST http://localhost:8000/api/brands/{id}/gt-collect \
  -H 'Authorization: Bearer <token>'

# Trigger GEO collection (async)  
curl -X POST http://localhost:8000/api/brands/{id}/collections \
  -H 'Authorization: Bearer <token>'

# Generate reports
curl -X POST http://localhost:8000/api/dashboard/brands/{id}/reports/generate \
  -H 'Authorization: Bearer <token>'
```

---

## 7-Page Operations Dashboard

| Page | Route | Purpose |
|------|-------|---------|
| Brand Overview | `/brands/{id}` | AI health score ring chart + 10 KPI cards + blocking issues + top risks + priority actions |
| GT Review | `/brands/{id}/gt-review` | Field-level review with evidence chains, source tier badges, conflict detection, promote readiness |
| AI Evidence | `/brands/{id}/evidence` | AI responses linked to KPI contributions, hallucinations, and action themes |
| Hallucination Risk | `/brands/{id}/hallucinations` | Multi-dimensional clustering (error_type × severity × field × dimension) + human review workflow |
| Action Workbench | `/brands/{id}/actions` | Kanban board with 9-status transitions + role-gated permission guards |
| Content Management | `/brands/{id}/content` | Risk-graded content pieces with sentence-level fact source mapping + publishing checklist |
| Trends & Attribution | `/brands/{id}/trends` | Line charts with event markers + action effect verification table + 6-type attribution labels |

**Design System:** Data-Dense Dashboard · Navy #1E40AF / Blue #3B82F6 / Amber #F59E0B · Fira Code + Fira Sans · Heroicons SVG

---

## API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Register new organization + admin user |
| `/api/auth/login` | POST | Login, returns JWT token |
| `/api/brands` | GET/POST | List / Create brands |
| `/api/brands/{id}/gt-collect` | POST | Trigger GT auto-collection (async) |
| `/api/brands/{id}/collections` | POST | Trigger GEO collection (async) |
| `/api/gt-candidates/{id}/review` | POST | Review GT candidate fields |
| `/api/gt-candidates/{id}/promote` | POST | Promote GT candidate to active |
| `/api/dashboard` | GET | Organization-level dashboard summary |
| `/api/brands/{id}/overview` | GET | Brand-level overview with 10 KPIs |
| `/api/brands/{id}/gt-review` | GET | GT review data |
| `/api/brands/{id}/evidence` | GET | AI evidence with KPI/hallucination linkage |
| `/api/brands/{id}/hallucinations` | GET | Hallucination results with filters |
| `/api/brands/{id}/action-themes` | GET | Action themes for Kanban |
| `/api/action-themes/{id}/transition` | POST | State transition with role guard |
| `/api/brands/{id}/trends` | GET | Trend data for charts |
| `/api/brands/{id}/attribution` | GET | Attribution analysis data |
| `/api/dashboard/brands/{id}/reports/generate` | POST | Generate report package |

---

## Architecture Decisions

**Why GT Three-Layer Model?**
AI-collected facts cannot be used directly for KPI calculation — they may contain errors or conflicts. The system enforces: Candidate (auto-collected) → Evidence (S/A/B/C/D tiered sources) → Review (human field-level confirmation) → Promote (active GT).

**Why Source Tier System (S/A/B/C/D)?**
Not all sources are equal. Official websites (S-tier, weight 1.0) can be used directly; AI platform responses (C-tier, weight 0.2) are only clues. High-risk fields (official_name, positioning, pricing, certifications) require S-tier evidence + human confirmation.

**Why ViewModel Layer?**
All number formatting, status judgment, and permission calculation happens in Python ViewModels. Jinja2 templates only loop and conditionally render — zero business logic. This makes templates stable, testable, and resilient to ORM changes.

**Why Async Celery Architecture?**
Brand collection (66 AI calls) and GT collection (30 AI calls) run in Celery workers. API immediately returns `202 + task_id`, avoiding HTTP timeouts. Lesson from Phase 9: synchronous execution took 17 minutes and timed out.

**Why Not Auto-Publish?**
Generated content passes fact-checking (GT field verification + forbidden claims detection), but final publishing decisions must be human-made. All content receives risk grading (low → standard review / medium → brand review / high → legal review).

---

## Current Status

### Completed — P0 Production Readiness

- [x] **P0-1** Trusted Fact Engineering — S/A/B/C/D source tier system with field-level evidence requirements
- [x] **P0-2** KPI Explainability — All 10 KPIs return numerator/denominator/confidence with detail cards
- [x] **P0-3** Semantic Hallucination Detection — 9 error types with human review workflow
- [x] **P0-4** Action Aggregation — Theme clustering with max 10 priority themes
- [x] **P0-5** Content Governance — Risk grading (low/medium/high) with CONTENT_PACKAGE_TRANSITIONS state machine
- [x] **P0-6** Dashboard Workbench — 7-page operations dashboard with 6 user roles and 8 state patterns

### In Progress — P1

- [ ] **P1-1** Action Effect Attribution — 60% (logic exists, UI placeholder)
- [ ] **P1-2** Industry Templates — Not started (Finance/F&B/SaaS/EV)
- [ ] **P1-3** RBAC & Audit Logs — 50% (role guards exist, no audit trail)
- [ ] **P1-4** Cost & API Monitoring — Not started
- [ ] **P1-5** Queue Reliability — Not started
- [ ] **P1-6** Customer-Facing Report Language — Not started

### P2 — Commercialization

- [ ] Benchmark & Competitor Attribution
- [ ] Long-term Trend Analysis
- [ ] Automated Report Productization
- [ ] CMS Publishing Integration
- [ ] Multi-tenant SaaS

---

## Team Collaboration

See [SYNC_GUIDE.md](SYNC_GUIDE.md) for detailed instructions on:

- What syncs via Git vs what doesn't (API keys, database data, virtualenv)
- New member onboarding in 10 minutes
- Daily pull/push workflow
- Database migration synchronization
- How to share database dumps when needed

### Quick Rules

| Sync via Git | Do NOT sync |
|-------------|-------------|
| `src/` (all source code) | `.env` (API keys) |
| `tests/` (all tests) | `.venv/` (virtualenv) |
| `alembic/` (migrations) | `reports/` (runtime outputs) |
| `docs/` (specs + plans) | `pgdata/` (PostgreSQL data) |
| `deploy/` (service files) | `dump.rdb` (Redis data) |

---

## License

MIT

---

*GEO Explorer · Phase 12 · 112 tests · 0 failures · 92 Python files · 21 templates · 70+ commits*
