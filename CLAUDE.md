# GEO Explorer

品牌 AI 可见度监测与优化平台。Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Celery+Redis / PostgreSQL 16 / Jinja2+HTMX。

## 项目状态

**全部完成。769 tests (0 skipped, 0 failures)。零技术债。前后端按钮全审计通过（200+按钮→API）。CodeGraph 索引完整（268文件/3501节点/6049边）。GitHub: https://github.com/05ffh/GEO-Explorer**

## 完整链路

```
GT采集(S/A/B/C/D) → GT审核 → 品牌GEO采集 → 模板健康前置门槛 → 模板版本钉定
→ 5KPI + 5扩展KPI → 4层幻觉分类 → ClaimNature v2
→ 多证据GT → 行业KPI权重 → 样本充分度
→ Action Theme → Content Package(含平台变体) → 报告质量Summary
→ Go/No-Go → 三格式报告 → 历史重归因 → 人审闭环
```

## AI 平台内容适配层

```
Content Package (品牌无关事实)
  → Web适配器: 官网HTML + Schema.org JSON-LD (DeepSeek/Kimi)
  → Doubao适配器: 头条号SEO文章 + 百科卡片 (字节生态)
  → Wenxin适配器: 百度百科词条 + 百家号SEO长文 (百度生态)
  → Compliance Checker: 绝对化表述/广告腔/敏感词/参考资料
  → 10态发布状态机: draft→generated→needs_review→...→published→outdated
  → 前端工作台: /brands/{id}/content/{cp_id}/platform-variants
```

## GT 采集与验证

```
AI采集(4平台并发) → 搜索采集(Tavily+DuckDuckGo并发)
→ 高风险字段定向Tavily验证(5 P0锚点字段)
→ 跨源验证(仅S/A/B搜索源可升级AI, AI永不升S)
→ Tavily answer summary evidence(tier B max)
→ GroundTruthEvidence → pending_review → approve/reject(AuditLog) → GT anchor
```

## 字段分层策略

| 策略 | 字段 | AI | 搜索 | 人审 |
|------|------|:--:|:--:|:--:|
| search_first | official_name, founded_year, official_domains, forbidden_claims | 不允许 | 必须 | 必须 |
| search_verify | headquarters | 允许 | 必须 | 必须 |
| search_plus_ai | core_products, industry, category | 允许 | 必须 | 部分 |
| ai_plus_search | positioning, key_differentiators, target_users, core_scenarios, target_competitors | 允许 | 可选 | 部分 |

## 执行模式

`TASK_EXECUTION_MODE=diagnostic|celery` × `CELERY_WORKER_POOL=solo|prefork`
- diagnostic: 单进程 async inline, 不阻塞 HTTP
- celery_solo: Celery 单进程 (开发/生产默认)
- celery_prefork: Celery 多进程 (需 fork-safe client)
- 诊断脚本: `scripts/run_collection_diagnostic.py`

## 设计系统

Data-Dense Dashboard, #1E40AF/#3B82F6/#F59E0B, Fira Code+Fira Sans, Jinja2+HTMX+Tailwind CDN+Chart.js+Heroicons

## 关键路径

- 项目: `/home/ffh/explore geo/`, symlink `/home/ffh/geo-explorer`
- API: http://localhost:8000/login
- DB: Docker `exploregeo-db-1:5432` / test `exploregeo-test_db-1:5433`
- Redis: systemd `geo-redis:6379`
- Systemd: `geo-redis`, `geo-celery`(--pool=solo), `geo-api`
- WSL 一键启动: `bash ~/start-geo.sh`
- 诊断: `.venv/bin/python scripts/run_collection_diagnostic.py <brand_id>`
- 测试: `.venv/bin/pytest tests/ --ignore=tests/e2e` (769 passed, 0 skipped)
- sudo: 050618
- Celery健康: `curl http://localhost:8000/system/celery-health`
- CodeGraph: 268 files, 3,501 nodes, 6,049 edges

## 平台配置 (WSL2 dev)

| 平台 | 并发 | RPM | TPM | 状态 |
|------|:--:|:--:|:--:|:--:|
| DeepSeek | 2 | — | — | healthy |
| Kimi | 2 | 60 | 800K | healthy |
| Doubao | 2 | 300 | 1.5M | healthy |
| Wenxin | 2 | 30 | 500K | healthy |

## 搜索后端

| 后端 | 状态 | 用途 |
|------|:--:|------|
| Tavily | ✅ running | GT验证主源 + 字段定向搜索 |
| DuckDuckGo | ✅ running | fallback, tier上限A |
| Google CSE | ❌ GCP未启用 | 已摘除, 等待启用后接回 |
| Brave | ❌ 无Key | 等待API Key申请 |

## 长期待办 (3项)

- Brave Search API Key 申请 + 接入
- Google CSE API 在 GCP 启用
- P2-1: 多轮共识 + 时间衰减
