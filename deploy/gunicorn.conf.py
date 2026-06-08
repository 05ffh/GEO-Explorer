"""Gunicorn production configuration for GEO Explorer (P0-3).

Usage:
    gunicorn src.main:app -c deploy/gunicorn.conf.py

All numeric params are overrideable via environment variables.
"""

import multiprocessing as mp
import os

# ── Bind ──────────────────────────────────────────────────────────────────────
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# ── Workers ───────────────────────────────────────────────────────────────────
# UvicornWorker for FastAPI async support.
worker_class = "uvicorn.workers.UvicornWorker"
workers = int(os.getenv("WEB_CONCURRENCY", str(mp.cpu_count() * 2 + 1)))

# preload_app=False avoids async connection pool issues with SQLAlchemy 2.0 async
preload_app = False

# ── Timeouts ──────────────────────────────────────────────────────────────────
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# ── Worker lifecycle ─────────────────────────────────────────────────────────
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "100"))

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog = "-"      # stdout
errorlog = "-"       # stderr
loglevel = os.getenv("LOG_LEVEL", "info")

# Structured access log format (JSON-compatible)
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" %(D)sus'
)

# ── Security ──────────────────────────────────────────────────────────────────
# Use /dev/shm for worker temp files (in-memory, no disk writes)
worker_tmp_dir = "/dev/shm"

# Drop privileges after binding (if started as root)
user = os.getenv("APP_USER", "")
group = os.getenv("APP_GROUP", "")
