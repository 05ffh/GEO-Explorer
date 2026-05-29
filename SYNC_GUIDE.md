# GEO Explorer — 团队同步指南

## 什么通过 Git 同步，什么不

```
                        Git 仓库
                   ┌─────────────────┐
        ✅ 同步     │  src/           │     ❌ 不同步
                   │  tests/         │
  源代码            │  alembic/       │    数据库里的品牌数据
  模板文件          │  docs/          │    API Key (.env)
  数据库迁移        │  deploy/        │    虚拟环境 (.venv)
  设计规范          │  requirements.txt│   Redis 缓存数据
  实现计划          │  setup.sh       │    生成的报告文件
  测试              │  SYNC_GUIDE.md  │    本地 IDE 配置
  服务配置          │  CLAUDE.md      │    本地操作系统文件
                   │  .env.example   │
                   │  .gitignore     │
                   └─────────────────┘
```

## 新成员从零搭建（10 分钟）

```bash
# 1. 克隆代码
git clone <仓库地址> geo-explorer
cd geo-explorer

# 2. 一键初始化（自动完成: venv → 依赖 → .env → 数据库迁移）
bash setup.sh

# 3. 编辑 .env，填入自己的 API Key
nano .env
# 填入: DEEPSEEK_API_KEY=sk-xxx / KIMI_API_KEY=sk-xxx / DOUBAO_API_KEY=xxx

# 4. 启动
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# 5. 浏览器打开
# http://localhost:8000/login → 注册/登录 → 品牌总览
```

## 日常协作流程

### 每天开始工作前
```bash
git pull origin master          # 拉取最新代码
.venv/bin/python -m alembic upgrade head  # 同步数据库结构（如有新 migration）
```

### 完成一个功能后
```bash
git add -A
git commit -m "feat: xxx 功能描述"
git push origin master
```

### 数据库结构有变化时
```bash
.venv/bin/python -m alembic revision --autogenerate -m "描述这次改了什么"
# 检查生成的 migration 文件，去掉无关的 alter_column
git add alembic/versions/
git commit -m "migration: 描述"
git push
```

### 冲突处理
```bash
git pull origin master          # 如果冲突
# 手动解决冲突文件
git add .
git commit -m "merge: 解决冲突"
git push
```

## 不能同步的东西 — 怎么处理

| 不能同步 | 为什么 | 怎么处理 |
|---------|--------|---------|
| **API Key (.env)** | 每人密钥不同，且不能泄露 | 每人从 `.env.example` 复制后填入自己的 Key |
| **PostgreSQL 数据** | 品牌数据、采集结果、GT 数据是运行时产物 | 每人独立触发采集生成自己的数据；或导出/导入 SQL dump |
| **Redis 数据** | 任务队列运行时状态 | 重启后自动清空，无需同步 |
| **.venv 虚拟环境** | 平台相关（Ubuntu vs macOS 二进制不同） | 每人执行 `bash setup.sh` 自动重建 |
| **reports/ 报告** | 诊断报告是运行时产物，每次生成不同 | 需要分享报告时，单独发送 PDF 文件 |
| **Node.js 全局包** | Puppeteer + marked 是系统级安装 | 每人手动安装一次: `npm i -g puppeteer marked` |

## 如果要分享数据库数据

```bash
# 导出（你的机器）
pg_dump -U geo -h localhost geo_explorer > geo_explorer_dump.sql

# 导入（同事的机器）
psql -U geo -h localhost geo_explorer < geo_explorer_dump.sql
```

注意：数据库 dump 文件很大，不要提交到 git。通过网盘/飞书传输。
