# GEO Explorer

品牌 AI 可见度监测与优化平台。Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Celery+Redis / PostgreSQL 16 / Jinja2+HTMX。

## 项目状态

**全部完成。654 tests (3 skipped, 0 failures)。Mock 测试体系就绪。GitHub: https://github.com/05ffh/GEO-Explorer**

Phase A + P0 7-10 + P1 1-10 + P2 1-4 + 前端架构补齐 + ClaimNature v2 + 5 模块前端补齐 + 集成审计 + 平台限流治理 + Mock 测试体系。

## 完整链路

```
GT采集(S/A/B/C/D) → GT审核 → 品牌GEO采集 → 模板健康前置门槛 → 模板版本钉定
→ 5KPI + 5扩展KPI → 4层幻觉分类 → ClaimNature v2
→ 多证据GT → 行业KPI权重 → 样本充分度
→ Action Theme → Content Package → 报告质量Summary → Go/No-Go
→ 三格式报告 → 历史重归因 → 人审闭环
```

## 工作流

spec → 桌面审阅 → 补齐清单 → 吸收 → Build → 验证，可跳过 Plan。TDD 铁律。前端按钮必须有真实 API，不做假按钮。

## 设计系统

Data-Dense Dashboard, #1E40AF/#3B82F6/#F59E0B, Fira Code+Fira Sans, Jinja2+HTMX+Tailwind CDN+Chart.js+Heroicons

## 关键路径

- 项目: `/home/ffh/explore geo/`, symlink `/home/ffh/geo-explorer`
- API: http://localhost:8000/login
- DB: Docker `exploregeo-db-1:5432` / test `exploregeo-test_db-1:5433`
- Redis: systemd `geo-redis:6379`
- Systemd: `geo-redis`, `geo-celery`, `geo-api`
- WSL 一键启动: `bash ~/start-geo.sh`
- 测试: `pytest tests/ --ignore=tests/e2e` (654 passed)
- sudo: 050618

## 架构要点

- **adapter_registry 依赖注入** — `run_collection()` 接受 `adapter_registry` 参数，测试不碰全局 ADAPTERS
- **MockPlatformAdapter** — 9 模式 (success/rate_limited/timeout/auth_failed/quota_exhausted/empty_response/parse_failed/network_error/mixed)
- **COLLECTION_TEST_MODE** — mock(默认)/real，前端 banner 显示当前模式，real 模式触发采集前二次确认
- **平台限流** — 429 → platform_rate_limited 独立分类，Retry-After + exponential backoff + jitter + cooldown
- **Wenxin** — `bce-v3/ALTAK-` 自动检测 Bearer 认证，当前 API Key 有效
- **WSL2 并发** — 每平台 2 semaphore，共享 httpx client (connect=20s, read=90s)

## 平台配置 (WSL2 dev)

| 平台 | 并发 | RPM | TPM | 状态 |
|------|:--:|:--:|:--:|:--:|
| DeepSeek | 2 | — | — | healthy |
| Kimi | 2 | 60 | 800K | healthy |
| Doubao | 2 | 300 | 1.5M | healthy |
| Wenxin | 2 | 30 | 500K | healthy |

## 历史 Bug 清单 (已全部修复)

| Bug | 文件 |
|------|------|
| `_page_context` current_page 关键字重复 → 14 页面 500 | `main.py` |
| Jinja2 `vm.xxx` dict 方法冲突 | queue_monitor + publishing 模板 |
| `add_audit_log(None)` → Celery DLQ 崩溃 | `services/audit.py` |
| `_PreflightResult` 参数名不匹配 → 全部模板误判 invalid | `collector/engine.py` |
| `_build_template_health_report` 不接受 QueryTemplate | `collector/engine.py` |
| Dashboard `collection-runs` → 应为 `collections` | `dashboard/index.html` |
| `deliver_customer_reports` 不存在 | `main.py` |
| `sum(status=="success")` SQL 表达式错误 | `view_models/run_detail.py` |
| 共享 `ADAPTERS` 全局字典异步竞态 → 测试卡死 | 已改为 adapter_registry 注入 |

## 长期待办

- Tavily API Key 申请 + 接入
- Brave Search API Key 申请 + 接入
- GT Search 前端页面 `/brands/{id}/gt-search`
- Wenxin RPM/TPM/TPD 实际限额确认
- GT 来源升级 C→S/A/B
- 生产部署基础设施 (TLS/nginx/gunicorn/DB备份/CI)
