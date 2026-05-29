# GEO Explorer

品牌 AI 可见度监测与优化平台。Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Celery+Redis / PostgreSQL 16 / Jinja2+HTMX。

**全程「工程师」模式推进**（Define→Plan→Build→Verify→Review→Ship），不跳过任何阶段。

## 项目状态

Phase 10 已完成，60 commits，89 tests (0 failures)，83 源文件。完整链路已打通：

```
GT采集 → GT审核 → 品牌GEO采集 → 10KPI+幻觉检测 → Action Plans → Content Package → 报告(.md/.docx/.pdf)
```

## 项目文档

- 完整介绍: `reports/GEO_Explorer_项目介绍.md` (PDF 也在同目录)
- 设计规范: `docs/superpowers/specs/`
- 实现计划: `docs/superpowers/plans/`
- 长期记忆: `/home/ffh/.claude/projects/-home-ffh/memory/`（用户输入"GEO"触发加载）

## Retrospectives

每次开发任务前:
1. 读取 `docs/retrospectives/INDEX.md`
2. 搜索与当前任务关键词相关的复盘记录
3. 在实现说明中列出已参考的教训
4. 若本次踩坑超过 30 分钟，按 TEMPLATE.md 格式新增 retrospective 并更新 INDEX.md

## CodeGraph

此项目已初始化 CodeGraph 索引。使用 `codegraph_*` 工具进行结构性代码探索，优于 grep。

## 关键路径

- 项目根目录: `/home/ffh/explore geo/`
- symlink: `/home/ffh/geo-explorer` → `/home/ffh/explore geo`（避免路径空格）
- PostgreSQL: localhost:5432（geo/geo, geo_explorer）
- Redis: localhost:6379
- Systemd 服务: `geo-redis`, `geo-celery`, `geo-api`（`sudo systemctl {start,stop,restart} geo-*`）
- 品牌报告输出: `reports/{品牌}_{日期}/`

## 环境

- .venv 在项目根目录
- Node.js 22 通过 nvm（`~/.nvm/versions/node/v22.22.2/bin`），Puppeteer+marked 已安装
- md2pdf 命令: `md2pdf <input.md> [output.pdf]`
