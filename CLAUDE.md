# GEO Explorer

品牌 AI 可见度监测与优化平台。Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Celery+Redis / PostgreSQL 16 / Jinja2+HTMX。

**全程「工程师」模式推进**（Define→Plan→Build→Verify→Review→Ship），不跳过任何阶段。

## 项目状态

**Phase A + P0 7-10 + P1 1-10 + P2-1 全部完成。555 tests (0 failures)。GitHub: https://github.com/05ffh/GEO-Explorer**

完整链路:
```
GT采集(含S/A/B/C/D来源等级) → GT审核(证据+人工双重阻断) → 品牌GEO采集
→ 模板健康前置门槛(P0-8) → 模板版本钉定(P1-7) → 5KPI(模板→指标绑定P0-9)
→ 4层幻觉分类(P0-7) → LLM-as-Judge(P1-6) → Debug Evidence(P1-5)
→ Claim Taxonomy(P2-1): FACT/OPINION/SPECULATION 三分类 + 独立风险判定
→ 行业KPI权重+阈值(P1-9) → 样本充分度评估(P1-10)
→ Action Theme聚合 → Content Package(风险分级+状态机)
→ 报告质量Summary → Go/No-Go → 报告(.md/.docx/.pdf)
→ 历史重归因(P1-8): original vs corrected 双视图
```

**下一步:** P2-2 多证据 GT

**P1/P2 推进流程:** spec → 发桌面审阅 → 用户发回补齐清单 → 完全吸收 → Build → 有效性验证

**设计系统:** Data-Dense Dashboard, #1E40AF/#3B82F6/#F59E0B, Fira Code+Fira Sans, Jinja2+HTMX+Tailwind CDN+Chart.js+Heroicons

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
- PostgreSQL: Docker 容器 `exploregeo-db-1` (postgres:16-alpine) localhost:5432（geo/geo, geo_explorer）/ `exploregeo-test_db-1` localhost:5433（geo_test/geo_test, geo_explorer_test）。启动: `docker start exploregeo-db-1 exploregeo-test_db-1`
- Redis: 系统服务 `geo-redis` localhost:6379，启动: `sudo systemctl start geo-redis`
- Systemd 服务: `geo-redis`, `geo-celery`, `geo-api`（`sudo systemctl {start,stop,restart} geo-*`）
- 品牌报告输出: `reports/{品牌}_{日期}/`
- Alembic 多库: `alembic.ini` 指向主库 5432。迁移测试库需 `DATABASE_URL=... alembic upgrade <rev>`。测试库需单独 stamp 跳过已存在的列。Alembic 有双 head (旧 chain 0da168569f6d + 新 chain)，不能 merge，用具体 revision 升级。
- sudo 密码: 050618

## 环境

- .venv 在项目根目录
- Node.js 22 通过 nvm（`~/.nvm/versions/node/v22.22.2/bin`），Puppeteer+marked 已安装
- md2pdf 命令: `md2pdf <input.md> [output.pdf]`
