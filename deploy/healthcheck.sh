#!/usr/bin/env bash
# GEO Explorer — Comprehensive health check (P0-8)
# Usage: ./deploy/healthcheck.sh
# Checks: app /health, /health/live, DB, Redis, Celery worker, Nginx

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/../docker-compose.prod.yml"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
HOST="${HEALTHCHECK_HOST:-localhost}"
PORT="${HEALTHCHECK_PORT:-80}"

FAIL=0

check() {
    local desc="$1"; shift
    if "$@" > /dev/null 2>&1; then
        echo -e "  ${GREEN}[OK]${NC} $desc"
    else
        echo -e "  ${RED}[FAIL]${NC} $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== GEO Explorer Health Check ==="

# ── App ────────────────────────────────────────────────────────────────────────
echo "App:"
check "GET /health/live"  curl -sf "http://${HOST}:${PORT}/health/live"
check "GET /health/ready" curl -sf "http://${HOST}:${PORT}/health/ready"
check "GET /health"      curl -sf "http://${HOST}:${PORT}/health"

# ── Database ───────────────────────────────────────────────────────────────────
echo "Database:"
PG_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q postgres 2>/dev/null || echo "")
if [ -n "$PG_CONTAINER" ]; then
    check "postgres running" docker exec "$PG_CONTAINER" pg_isready -U geo -d geo_explorer
else
    echo "  [SKIP] postgres container not found via compose"
fi

# ── Redis ──────────────────────────────────────────────────────────────────────
echo "Redis:"
REDIS_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q redis 2>/dev/null || echo "")
if [ -n "$REDIS_CONTAINER" ]; then
    check "redis running" docker exec "$REDIS_CONTAINER" redis-cli ping
else
    echo "  [SKIP] redis container not found via compose"
fi

# ── Celery ─────────────────────────────────────────────────────────────────────
echo "Celery:"
CELERY_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q celery-worker 2>/dev/null || echo "")
if [ -n "$CELERY_CONTAINER" ]; then
    check "celery worker running" docker exec "$CELERY_CONTAINER" celery -A src.celery_app inspect ping -d "celery@${CELERY_CONTAINER}" -t 5
else
    echo "  [SKIP] celery container not found"
fi

# ── Nginx ──────────────────────────────────────────────────────────────────────
echo "Nginx:"
NGINX_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q nginx 2>/dev/null || echo "")
if [ -n "$NGINX_CONTAINER" ]; then
    check "nginx running" docker exec "$NGINX_CONTAINER" nginx -t
else
    echo "  [SKIP] nginx container not found"
fi

# ── Result ─────────────────────────────────────────────────────────────────────
echo ""
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}All health checks passed.${NC}"
    exit 0
else
    echo -e "${RED}${FAIL} health check(s) failed.${NC}"
    exit 1
fi
