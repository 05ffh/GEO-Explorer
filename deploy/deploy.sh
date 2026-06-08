#!/usr/bin/env bash
# GEO Explorer — Production deploy (P0-4)
# Usage: ./deploy/deploy.sh
# Steps: preflight → backup → git pull → build → migrate → restart → healthcheck

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}/.."
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.prod.yml"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=== GEO Explorer Deploy ==="
echo "[$(date '+%H:%M:%S')] Working: $(pwd)"

# ── 0. Preflight ──────────────────────────────────────────────────────────────
if [ -x "${SCRIPT_DIR}/preflight.sh" ]; then
    "${SCRIPT_DIR}/preflight.sh" || {
        echo -e "${RED}[FAIL] Preflight checks failed${NC}"
        exit 1
    }
fi

# ── 1. Record current state ──────────────────────────────────────────────────
PREVIOUS_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "[$(date '+%H:%M:%S')] Current SHA: ${PREVIOUS_SHA}"
echo "$PREVIOUS_SHA" > "${SCRIPT_DIR}/.previous_sha"

# ── 2. Backup database ────────────────────────────────────────────────────────
echo "[$(date '+%H:%M:%S')] Backing up database..."
"${SCRIPT_DIR}/backup.sh" || {
    echo -e "${RED}[FAIL] Backup failed — aborting deploy${NC}"
    exit 1
}

# ── 3. Git pull ───────────────────────────────────────────────────────────────
echo "[$(date '+%H:%M:%S')] Pulling latest code..."
git fetch origin
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
git pull --ff-only origin "$CURRENT_BRANCH" || {
    echo -e "${RED}[FAIL] git pull failed (non-fast-forward). Resolve manually.${NC}"
    exit 1
}
NEW_SHA=$(git rev-parse --short HEAD)
echo "[$(date '+%H:%M:%S')] Deploying: ${PREVIOUS_SHA} → ${NEW_SHA}"

# ── 4. Build images ───────────────────────────────────────────────────────────
echo "[$(date '+%H:%M:%S')] Building Docker images..."
docker compose -f "$COMPOSE_FILE" build --pull 2>&1 | tail -5 || {
    echo -e "${RED}[FAIL] Docker build failed${NC}"
    exit 1
}

# ── 5. Start dependencies ─────────────────────────────────────────────────────
echo "[$(date '+%H:%M:%S')] Starting postgres + redis..."
docker compose -f "$COMPOSE_FILE" up -d postgres redis
sleep 3

# ── 6. Run migrations ─────────────────────────────────────────────────────────
echo "[$(date '+%H:%M:%S')] Running migrations..."
docker compose -f "$COMPOSE_FILE" run --rm app alembic upgrade head 2>&1 || {
    echo -e "${RED}[FAIL] Migration failed. Check logs.${NC}"
    echo -e "${YELLOW}To rollback: ./deploy/rollback.sh${NC}"
    exit 1
}

# ── 7. Restart services ───────────────────────────────────────────────────────
echo "[$(date '+%H:%M:%S')] Restarting app + celery + nginx..."
docker compose -f "$COMPOSE_FILE" up -d app celery-worker nginx

# Wait for services to be ready
sleep 5

# ── 8. Health check ───────────────────────────────────────────────────────────
echo "[$(date '+%H:%M:%S')] Health check..."
if [ -x "${SCRIPT_DIR}/healthcheck.sh" ]; then
    "${SCRIPT_DIR}/healthcheck.sh" || {
        echo -e "${RED}[FAIL] Health check failed.${NC}"
        echo -e "${YELLOW}To rollback: ./deploy/rollback.sh${NC}"
        exit 1
    }
fi

# ── 9. Done ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}=== Deploy complete ===${NC}"
echo "   ${PREVIOUS_SHA} → ${NEW_SHA}"
echo "   docker compose -f docker-compose.prod.yml ps"
echo ""
echo "   To rollback: ./deploy/rollback.sh"
