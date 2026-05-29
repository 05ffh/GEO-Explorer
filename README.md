# GEO Explorer

[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/tests-112_passed-brightgreen)](tests/)
[![Phase](https://img.shields.io/badge/phase-12-orange)]()
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Monitor how AI platforms describe your brand. Detect errors. Fix them. Verify the fix worked.**

---

## What is this?

When a potential customer asks an AI — "best coffee brands?" or "top project management tools?" — does the AI mention your brand? Does it describe you correctly? Or does it make things up?

GEO Explorer answers these questions systematically. It queries multiple AI platforms (DeepSeek, Kimi, Doubao), compares their answers against a verified fact database (Ground Truth), detects hallucinations, generates corrective content, and verifies that the fix actually worked.

Think of it as **SEO for the AI era** — but instead of optimizing for Google's algorithm, you're optimizing for how AI models understand and describe your brand.

---

## The Problem

| Problem | Real-world Example |
|---------|-------------------|
| AI gets your facts wrong | AI says Starbucks is a "cheap convenience store coffee" |
| AI doesn't mention you at all | "Best CRM tools" → lists 5 competitors, misses yours |
| AI recommends competitors first | Your product is better but AI doesn't know why |
| You fix your website but AI doesn't notice | Published corrected content months ago, AI still repeats old errors |
| You can't measure it | No way to know if your GEO efforts are working |

---

## How It Works

```
1. Build Ground Truth  →  Auto-collect facts about your brand from search + AI, then human review
2. Monitor AI Answers  →  Query 3+ AI platforms with 22 standardized question templates
3. Analyze & Detect    →  10 KPIs + 9 types of hallucination detection
4. Generate Content    →  LLM creates corrective content packages with fact-checking
5. Deliver & Verify    →  Export reports (.md/.docx/.pdf), re-test to measure improvement
```

Each piece of data is traced back to its source — you always know **where a fact came from** and **how confident we are in it**.

---

## What's Built

- **Ground Truth Engine** — Auto-collects brand facts with S/A/B/C/D source tier ratings. Field-level evidence trails. Conflict detection. Human review workflow before anything enters the fact database.
- **Multi-Platform Collection** — 22 query templates × 5 dimensions × 3 AI platforms. Async Celery tasks with rate limiting and retry logic.
- **10 KPI Analytics** — Share of Voice, Accuracy, Completeness, Citation Rate, Scenario Recall, Semantic Stability, Differentiation, Cross-Platform Consistency, First Recommendation Rate, Recommendation Quality. Every KPI includes numerator/denominator/confidence.
- **Semantic Hallucination Detection** — 9 error types (identity, category, positioning, feature, competitor confusion, unsupported claims, outdated claims, overclaims, negative hallucinations). Human review workflow.
- **Action Workbench** — Kanban board with 9-status lifecycle. Role-gated state transitions. Priority clustering (max 10 themes).
- **Content Packages** — LLM-generated corrective content with fact-checking against GT. Risk grading (low/medium/high). Schema.org JSON-LD generation. Publishing checklists.
- **7-Page Operations Dashboard** — Brand Overview, GT Review, AI Evidence, Hallucination Risk, Action Workbench, Content Management, Trends & Attribution. Jinja2 SSR + HTMX + Tailwind + Chart.js.
- **Report Delivery** — Diagnostic reports + optimization plans in `.md` / `.docx` / `.pdf` formats.
- **112 Tests, 0 Failures** — 92 Python source files, 21 Jinja2 templates, 22 database tables.

---

## Quick Start

```bash
git clone https://github.com/05ffh/GEO-Explorer.git
cd GEO-Explorer
bash setup.sh                         # venv → deps → .env → migrations
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000/login
```

**Prerequisites:** Python 3.12 · PostgreSQL 16 · Redis 7 · Node.js 22 (for PDF)

See [SYNC_GUIDE.md](SYNC_GUIDE.md) for team collaboration setup.

---

## Tech Stack

Python 3.12 · FastAPI · SQLAlchemy 2.0 async · PostgreSQL 16 · Celery + Redis 7 · Jinja2 + HTMX 2.0 + Tailwind CDN + Chart.js 4.4 · DeepSeek / Kimi / Doubao

---

## Where We Are

**Phase 12 complete** — all 6 P0 production-readiness items done. Working on P1 (effect attribution, audit logs, industry templates, cost monitoring, queue reliability, customer-facing reporting).

See [docs/](docs/) for design specs and implementation plans. See [geo-explorer-gaps](https://github.com/05ffh/GEO-Explorer) for the detailed maturity checklist.

---

## Project Structure

```
src/
├── models/         # 22 ORM data models
├── adapters/       # AI platform adapters
├── collector/      # Collection engine + GT auto-collector
├── analyzer/       # 10 KPI calculators + hallucination detector
├── actions/        # Action engine + content packages
├── api/            # REST API endpoints
├── search/         # DuckDuckGo + AI search backends
├── reports/        # Report generation + PDF/DOCX export
├── schemas/        # GT field definitions + source tier system
├── view_models/    # ViewModel layer (templates render only)
└── templates/      # 21 Jinja2 templates (7 pages + 11 components)
tests/              # 112 tests, 0 failures
alembic/            # Database migrations
deploy/             # systemd service files
docs/               # Design specs + implementation plans
```

---

## License

MIT
