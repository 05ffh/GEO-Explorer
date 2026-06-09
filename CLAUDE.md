# GEO Explorer

品牌 AI 可见度监测与优化平台。Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Celery+Redis / PostgreSQL 16 / Jinja2+HTMX。

## 项目状态

**全部完成。769 tests (0 skipped, 0 failures)。零技术债。GitHub: https://github.com/05ffh/GEO-Explorer**

Phase A + P0 7-10 + P1 1-10 + P2 1-4 + 前端架构补齐 + ClaimNature v2 + 5 模块前端补齐 + 集成审计 + 平台限流治理 + Mock 测试体系 + Tavily + Google Search + GT Search 完整链路 + 来源跨源验证 + GT 质量提升(P0-1/P0-2/P1-1/P1-2) + 生产部署基础设施 + Celery fork-safe 修复 + TaskExecutionMode 三模式 + 全测试覆盖(zero skip)。

## 完整链路

```
GT采集(S/A/B/C/D) → GT审核 → 品牌GEO采集 → 模板健康前置门槛 → 模板版本钉定
→ 5KPI + 5扩展KPI → 4层幻觉分类 → ClaimNature v2
→ 多证据GT → 行业KPI权重 → 样本充分度
→ Action Theme → Content Package → 报告质量Summary → Go/No-Go
→ 三格式报告 → 历史重归因 → 人审闭环
```

## GT 采集与验证

```
AI采集(4平台并发, semaphore=2) → 搜索采集(Tavily+DuckDuckGo并发)
→ 高风险字段定向Tavily验证(5 P0锚点字段)
→ 跨源验证(cross_validator: 字段级matcher, 仅S/A/B搜索源可升级AI, AI永不升S)
→ Tavily answer作为summary evidence(tier B max)
→ GroundTruthEvidence(125+行/轮)
→ pending_review candidate → approve/reject(AuditLog) → GroundTruthVersion
```

## 字段分层策略

| 策略 | 字段 | AI角色 | 搜索验证 | 人审 |
|------|------|:--:|:--:|:--:|
| search_first | official_name, founded_year, official_domains, forbidden_claims | 不允许 | 必须 | 必须 |
| search_verify | headquarters | 允许 | 必须 | 必须 |
| search_plus_ai | core_products, industry, category | 允许 | 必须 | 部分 |
| ai_plus_search | positioning, key_differentiators, target_users, core_scenarios, target_competitors | 允许 | 可选 | 部分 |

## 工作流

spec → 桌面审阅 → 补齐清单 → 吸收 → Build → 验证，可跳过 Plan。TDD 铁律。前端按钮必须有真实 API，不做假按钮。

## 设计系统

Data-Dense Dashboard, #1E40AF/#3B82F6/#F59E0B, Fira Code+Fira Sans, Jinja2+HTMX+Tailwind CDN+Chart.js+Heroicons

## 关键路径

- 项目: `/home/ffh/explore geo/`, symlink `/home/ffh/geo-explorer`
- API: http://localhost:8000/login
- DB: Docker `exploregeo-db-1:5432` / test `exploregeo-test_db-1:5433`
- Redis: systemd `geo-redis:6379`
- Systemd: `geo-redis`, `geo-celery`(--pool=solo), `geo-api`
- WSL 一键启动: `bash ~/start-geo.sh`
- 诊断脚本: `.venv/bin/python scripts/run_collection_diagnostic.py <brand_id> [org_id]`
- 测试: `.venv/bin/pytest tests/ --ignore=tests/e2e` (769 passed, 0 skipped)
- sudo: 050618

## 架构要点

- **adapter_registry 依赖注入** — `run_collection()` 接受 `adapter_registry` 参数，测试不碰全局 ADAPTERS
- **MockPlatformAdapter** — 9 模式 (success/rate_limited/timeout/auth_failed/quota_exhausted/empty_response/parse_failed/network_error/mixed)
- **COLLECTION_TEST_MODE** — mock(默认)/real，前端 banner 显示当前模式，real 模式触发采集前二次确认
- **平台限流** — 429 → platform_rate_limited 独立分类，Retry-After + exponential backoff + jitter + cooldown
- **Wenxin** — `bce-v3/ALTAK-` 自动检测 Bearer 认证，当前 API Key 有效
- **Celery fork-safe** — `os.getpid()` 进程级 HTTP client 缓存 + solo pool 默认 + worker_process_init/shutdown 信号
- **TaskExecutionMode** — 三模式: diagnostic(单进程async)/celery_solo/celery_prefork，通过 `TASK_EXECUTION_MODE` 配置
- **Execution Dispatcher** — 统一 GT/GEO 采集入口，diagnostic 模式 asyncio.create_task 不阻塞 HTTP
- **四层数据边界** — SearchResult → Evidence → Candidate → GT，AI source_type 永不改变
- **GT Quality Panel** — 审核页展示 S/A/B/C/D tier 分布 + anchor 统计

## 平台配置 (WSL2 dev)

| 平台 | 并发 | RPM | TPM | 状态 |
|------|:--:|:--:|:--:|:--:|
| DeepSeek | 2 | — | — | healthy |
| Kimi | 2 | 60 | 800K | healthy |
| Doubao | 2 | 300 | 1.5M | healthy |
| Wenxin | 2 | 30 | 500K | healthy |

## 历史 Bug 清单 (已全部修复, 19个)

| Bug | 文件 | 状态 |
|------|------|:--:|
| `_page_context` current_page 关键字重复 → 14 页面 500 | `main.py` | fixed |
| Jinja2 `vm.xxx` dict 方法冲突 | queue_monitor + publishing 模板 | fixed |
| `add_audit_log(None)` → Celery DLQ 崩溃 | `services/audit.py` | fixed |
| `_PreflightResult` 参数名不匹配 → 模板误判 invalid | `collector/engine.py` | fixed |
| `_build_template_health_report` 不接受 QueryTemplate | `collector/engine.py` | fixed |
| Dashboard `collection-runs` → 应为 `collections` | `dashboard/index.html` | fixed |
| `deliver_customer_reports` 不存在 | `main.py` | fixed |
| `sum(status=="success")` SQL 表达式错误 | `view_models/run_detail.py` | fixed |
| 共享 `ADAPTERS` 全局字典异步竞态 → 测试卡死 | adapter_registry 注入 | fixed |
| 嵌套 Semaphore 死锁 | 移除 global_sem | fixed |
| ForkPoolWorker + OpenAI SDK httpx 池 | shared client + connect=20s | fixed |
| Mock 测试 retry 30s delay 卡死 | max_retries=0 + fixture | fixed |
| `get_adapter` lambda factory 未调用 | `callable(factory)` | fixed |
| `pipeline.py` 缺少 `HallucinationResult` import | `pipeline.py` | fixed |
| `_collect_from_ai_platforms` 遗漏 Wenxin | `gt_collector.py` | fixed |
| `EmailStr` 拒绝 `.local` 域名 | `auth.py` (→ str) | fixed |
| `run_collection` MissingGreenlet | `engine.py` | fixed |
| Celery ForkPoolWorker httpx fork hang | `os.getpid()` cache + solo pool | fixed |
| `collect_gt_task` soft_time_limit=600 不够 | → 1800s | fixed |

## 长期待办

- Brave Search API Key 申请 + 接入
- Google CSE API 在 GCP 启用
- Wenxin RPM/TPM/TPD 实际限额确认
- P2-1: 多轮共识 + 时间衰减 (需多轮采集数据积累)
