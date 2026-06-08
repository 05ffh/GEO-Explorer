#!/usr/bin/env bash
# GEO Explorer — Generate production secrets (P0-7)
# Usage: ./deploy/generate-secrets.sh [--overwrite]
# Output: random keys for SECRET_KEY, POSTGRES_PASSWORD, JWT_SECRET, ENCRYPTION_KEY

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

if [ "${1:-}" = "--overwrite" ]; then
    OVERWRITE=true
else
    OVERWRITE=false
fi

echo "=== GEO Explorer Secret Generator ==="
echo ""

# ── Check if .env.production already exists ────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}/.."

if [ -f "${PROJECT_DIR}/.env.production" ] && [ "$OVERWRITE" = false ]; then
    echo -e "${YELLOW}.env.production already exists.${NC}"
    echo "To overwrite: ./deploy/generate-secrets.sh --overwrite"
    echo "Or manually add the keys below to your .env.production"
    echo ""
fi

# ── Generate secrets ───────────────────────────────────────────────────────────
SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
POSTGRES_PASSWORD=$(openssl rand -base64 24 2>/dev/null || python3 -c "import secrets; print(secrets.token_urlsafe(18))")
JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
ENCRYPTION_KEY=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")

if [ "$OVERWRITE" = true ] || [ ! -f "${PROJECT_DIR}/.env.production" ]; then
    cat > "${PROJECT_DIR}/.env.production" << EOF
# GEO Explorer — Production Environment (auto-generated $(date +%Y-%m-%d))
# WARNING: Contains secrets. chmod 600 this file.
# Re-generate with: ./deploy/generate-secrets.sh

# ── App ──────────────────────────────────────────────────────────────────────
APP_ENV=production
SECRET_KEY=${SECRET_KEY}
BASE_URL=https://your-domain.com
ALLOWED_HOSTS=your-domain.com
CORS_ORIGINS=https://your-domain.com

# ── Database ─────────────────────────────────────────────────────────────────
POSTGRES_USER=geo
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=geo_explorer
DATABASE_URL=postgresql+asyncpg://geo:${POSTGRES_PASSWORD}@postgres:5432/geo_explorer

# ── Redis ────────────────────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── JWT ──────────────────────────────────────────────────────────────────────
JWT_SECRET=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# ── Security ─────────────────────────────────────────────────────────────────
ENCRYPTION_KEY=${ENCRYPTION_KEY}
RATE_LIMIT_ENABLED=true
COOKIE_SECURE=true

# ── AI Platforms ─────────────────────────────────────────────────────────────
DEEPSEEK_API_KEY=
KIMI_API_KEY=
DOUBAO_API_KEY=
WENXIN_API_KEY=

# ── Search APIs ──────────────────────────────────────────────────────────────
TAVILY_API_KEY=
GOOGLE_CSE_API_KEY=
GOOGLE_CSE_CX=

# ── Feature Flags ────────────────────────────────────────────────────────────
COLLECTION_TEST_MODE=real
GT_SEARCH_TAVILY_ENABLED=true
GT_SEARCH_GOOGLE_CSE_ENABLED=false
GT_SEARCH_BRAVE_ENABLED=false
GT_SEARCH_DUCKDUCKGO_ENABLED=true
EOF
    chmod 600 "${PROJECT_DIR}/.env.production"
    echo -e "${GREEN}Generated .env.production with random secrets${NC}"
    echo -e "${YELLOW}IMPORTANT: Edit .env.production to set your domain name and API keys!${NC}"
else
    echo ""
    echo "Add to your .env.production:"
    echo "  SECRET_KEY=${SECRET_KEY}"
    echo "  POSTGRES_PASSWORD=${POSTGRES_PASSWORD}"
    echo "  JWT_SECRET=${JWT_SECRET}"
    echo "  ENCRYPTION_KEY=${ENCRYPTION_KEY}"
fi
