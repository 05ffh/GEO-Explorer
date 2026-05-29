#!/bin/bash
# ============================================================================
# GEO Explorer — 一键初始化脚本
# 用法: bash setup.sh
# 环境: Ubuntu/Debian (WSL2 or native), Python 3.12+
# ============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

echo "=============================================="
echo "  GEO Explorer — 项目初始化"
echo "=============================================="
echo ""

# ---- 0. 检查系统依赖 ----
log "检查系统依赖..."

# Python
python3 --version >/dev/null 2>&1 || err "请先安装 Python 3.12+"
log "Python $(python3 --version | cut -d' ' -f2)"

# PostgreSQL
which psql >/dev/null 2>&1 || warn "PostgreSQL 未安装，请手动安装后重试"
pg_isready -q 2>/dev/null && log "PostgreSQL 已运行" || warn "PostgreSQL 未运行，请执行: sudo systemctl start postgresql"

# Redis
which redis-server >/dev/null 2>&1 || warn "Redis 未安装，请手动安装后重试"

# Node.js (for PDF generation)
which node >/dev/null 2>&1 || warn "Node.js 未安装，PDF 生成功能不可用"
node --version 2>/dev/null && log "Node.js $(node --version)"

echo ""

# ---- 1. 创建虚拟环境 ----
log "创建 Python 虚拟环境..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    log ".venv 创建完成"
else
    warn ".venv 已存在，跳过创建"
fi

# ---- 2. 安装 Python 依赖 ----
log "安装 Python 依赖..."
.venv/bin/pip install -r requirements.txt -q
log "依赖安装完成"

# ---- 3. 配置环境变量 ----
log "配置环境变量..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        warn "已从 .env.example 创建 .env"
        warn ">>> 请编辑 .env 填入你的 API Key (DeepSeek/Kimi/豆包) <<<"
    else
        err ".env.example 不存在"
    fi
else
    warn ".env 已存在，跳过创建"
fi

# ---- 4. 初始化数据库 ----
log "初始化数据库..."
.venv/bin/python -m alembic upgrade head
log "数据库迁移完成"

echo ""
echo "=============================================="
echo "  初始化完成!"
echo "=============================================="
echo ""
echo "  后续步骤:"
echo "  1. 编辑 .env 填入 API Key:"
echo "     nano .env"
echo ""
echo "  2. 启动服务:"
echo "     .venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "  3. 浏览器打开:"
echo "     http://localhost:8000/login"
echo ""
echo "  4. 运行测试:"
echo "     .venv/bin/python -m pytest tests/ -v"
echo ""
