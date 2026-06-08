#!/usr/bin/env bash
# GEO Explorer — Rollback to previous deploy (P0-4)
# Usage: ./deploy/rollback.sh [target_sha]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}/.."
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

TARGET_SHA="${1:-}"

if [ -z "$TARGET_SHA" ]; then
    if [ -f "${SCRIPT_DIR}/.previous_sha" ]; then
        TARGET_SHA=$(cat "${SCRIPT_DIR}/.previous_sha")
    else
        echo -e "${RED}[ERROR] No target SHA specified and no .previous_sha found.${NC}"
        echo "Usage: ./deploy/rollback.sh <sha>"
        exit 1
    fi
fi

echo "=== GEO Explorer Rollback ==="
echo "[$(date '+%H:%M:%S')] Rolling back to: ${TARGET_SHA}"

# Backup before rollback
echo "[$(date '+%H:%M:%S')] Backing up database before rollback..."
"${SCRIPT_DIR}/backup.sh" --quiet 2>/dev/null || true

# Check if target SHA exists
if ! git cat-file -e "${TARGET_SHA}^{commit}" 2>/dev/null; then
    echo -e "${RED}[ERROR] SHA ${TARGET_SHA} not found in repository.${NC}"
    exit 1
fi

CURRENT_SHA=$(git rev-parse --short HEAD)

echo "[$(date '+%H:%M:%S')] Rolling back code: ${CURRENT_SHA} → ${TARGET_SHA}"
git checkout "$TARGET_SHA"

echo "[$(date '+%H:%M:%S')] Rebuilding and restarting..."
docker compose -f docker-compose.prod.yml build 2>&1 | tail -3
docker compose -f docker-compose.prod.yml up -d app celery-worker nginx

sleep 5

if [ -x "${SCRIPT_DIR}/healthcheck.sh" ]; then
    "${SCRIPT_DIR}/healthcheck.sh" || {
        echo -e "${YELLOW}[WARN] Health check after rollback failed. Manual intervention needed.${NC}"
        exit 1
    }
fi

echo -e "${GREEN}=== Rollback complete: ${TARGET_SHA} ===${NC}"
echo ""
echo -e "${YELLOW}NOTE: Database migrations were NOT rolled back.${NC}"
echo "If the previous deploy included irreversible migrations, run:"
echo "  alembic downgrade -1  # or specify target revision"
