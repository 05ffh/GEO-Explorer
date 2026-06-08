#!/usr/bin/env bash
# GEO Explorer — Preflight checks before deployment (P1-5)
# Usage: ./deploy/preflight.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}/.."
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

check() {
    local desc="$1"; shift
    if "$@" > /dev/null 2>&1; then
        echo -e "  ${GREEN}[PASS]${NC} $desc"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}[FAIL]${NC} $desc"
        FAIL=$((FAIL + 1))
    fi
}

warn() {
    echo -e "  ${YELLOW}[WARN]${NC} $1"
    WARN=$((WARN + 1))
}

echo "=== GEO Explorer Preflight ==="
echo ""

# ── Docker ────────────────────────────────────────────────────────────────────
echo "Docker:"
check "docker installed" command -v docker
check "docker daemon running" docker info
check "docker compose available" docker compose version
echo ""

# ── Environment ────────────────────────────────────────────────────────────────
echo "Environment:"
if [ -f .env ]; then
    check ".env exists" test -f .env
else
    warn ".env not found (using defaults from config.py)"
fi

if [ -f .env.production ]; then
    check ".env.production exists" test -f .env.production
    # Check for dev defaults in production
    if grep -q "change-me" .env.production 2>/dev/null; then
        warn ".env.production contains 'change-me' — generate real secrets!"
    fi
    if grep -q "SECRET_KEY=change-me" .env.production 2>/dev/null; then
        warn "SECRET_KEY is still 'change-me' — run deploy/generate-secrets.sh"
    fi
else
    warn ".env.production not found — copy .env.production.example and fill in values"
fi
echo ""

# ── Disk space ────────────────────────────────────────────────────────────────
echo "Disk:"
DISK_AVAIL=$(df -h . | tail -1 | awk '{print $4}')
DISK_PCT=$(df -h . | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$DISK_PCT" -gt 90 ]; then
    warn "Disk usage at ${DISK_PCT}% — available: ${DISK_AVAIL}"
else
    check "disk space (${DISK_AVAIL} available)" test "$DISK_PCT" -lt 90
fi
echo ""

# ── Git ────────────────────────────────────────────────────────────────────────
echo "Git:"
check "git repo clean" git diff --quiet
check "on master branch" test "$(git rev-parse --abbrev-ref HEAD)" = "master"
echo ""

# ── Config safety ─────────────────────────────────────────────────────────────
echo "Production safety:"
if grep -q "DEBUG=true\|DEBUG = true\|APP_ENV=development" docker-compose.prod.yml .env.production 2>/dev/null; then
    warn "DEBUG or development mode detected in production config"
else
    check "production mode" true
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "=== Result: ${PASS} passed, ${WARN} warnings, ${FAIL} failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo -e "${RED}Fix failures before deploying.${NC}"
    exit 1
fi
echo -e "${GREEN}Ready to deploy.${NC}"
