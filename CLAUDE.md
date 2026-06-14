# GEO Explorer

品牌 AI 可见度监测与优化平台。Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Celery+Redis / PostgreSQL 16 / Jinja2+HTMX。

## 项目状态

**全部完成。769 tests (0 skipped, 0 failures)。GitHub: https://github.com/05ffh/GEO-Explorer**

## 完整业务链路

```
GT采集(S/A/B/C/D) → GT审核 → 品牌GEO采集 → 模板健康前置门槛 → 模板版本钉定
→ 5KPI + 5扩展KPI → 4层幻觉分类 → ClaimNature v2
→ 多证据GT(加权共识+冲突分级) → 行业KPI权重+阈值 → 样本充分度
→ Action Theme → Content Package(含平台变体) → 报告质量Summary
→ Go/No-Go → 三格式报告(md+docx+pdf) → 历史重归因 → 人审闭环
```

## AI 平台内容适配层

```
Content Package (品牌无关事实)
  → Web适配器: 官网HTML + Schema.org JSON-LD (DeepSeek/Kimi)
  → Doubao适配器: 头条号SEO文章 + 百科卡片 (字节生态)
  → Wenxin适配器: 百度百科词条 + 百家号SEO长文 (百度生态)
  → Compliance Checker: 绝对化表述/广告腔/敏感词/参考资料检查
  → 发布状态机: draft→generated→needs_review→approved→published→outdated→archived
  → 前端工作台: /brands/{id}/content/{cp_id}/platform-variants
```

## GT 采集与验证体系

### 采集流程
```
AI采集(4平台并发, semaphore=2) → 搜索采集(Tavily+DuckDuckGo并发)
→ 高风险字段定向Tavily验证(5 P0锚点字段)
→ 跨源验证(cross_validator + field matchers)
→ Tavily answer summary evidence(tier B max)
→ GroundTruthEvidence → pending_review → approve/reject(AuditLog) → GT anchor
```

### Tier 升降级规则
| 条件 | AI evidence tier |
|------|:--:|
| S级搜索源确认 | A (AI永不升S) |
| A级/≥2 B级确认 | B |
| C级搜索源 | C (weak_support) |
| D级/禁用源 | C (不升级) |
| ≥2 A/B/S冲突 | D (contradicted) |

### 字段分层策略
| 策略 | 字段 | AI | 搜索验证 | 人审 |
|------|------|:--:|:--:|:--:|
| search_first | official_name, founded_year, official_domains, forbidden_claims | 不允许 | 必须 | 必须 |
| search_verify | headquarters | 允许 | 必须 | 必须 |
| search_plus_ai | core_products, industry, category | 允许 | 必须 | 部分 |
| ai_plus_search | positioning, key_differentiators, target_users, core_scenarios, target_competitors | 允许 | 可选 | 部分 |

## 执行模式

`TASK_EXECUTION_MODE=diagnostic|celery` × `CELERY_WORKER_POOL=solo|prefork`

- **diagnostic**: 单进程 async inline, 不阻塞 HTTP（用于调试/紧急绕过）
- **celery_solo**: Celery 单进程（开发/生产默认，不 fork，HTTP client 安全）
- **celery_prefork**: Celery 多进程（生产扩容，需 fork-safe client 初始化）
- execution_dispatcher 统一 GT/GEO 采集入口
- 诊断脚本: `scripts/run_collection_diagnostic.py`

## 工作流

spec → 桌面审阅 → 补齐清单 → 吸收 → Build → 验证，可跳过 Plan。TDD 铁律。前端按钮必须有真实 API。

## 设计系统

Data-Dense Dashboard, #1E40AF/#3B82F6/#F59E0B, Fira Code+Fira Sans, Jinja2+HTMX+Tailwind CDN+Chart.js+Heroicons

## 关键路径

| 资源 | 路径 |
|------|------|
| 项目 | `/home/ffh/explore geo/`, symlink `/home/ffh/geo-explorer` |
| API | http://localhost:8000/login |
| DB | Docker `exploregeo-db-1:5432` / test `exploregeo-test_db-1:5433` |
| Redis | systemd `geo-redis:6379` |
| Systemd | `geo-redis`, `geo-celery`(--pool=solo), `geo-api` |
| 启动 | `bash ~/start-geo.sh` |
| 诊断 | `.venv/bin/python scripts/run_collection_diagnostic.py <brand_id>` |
| Celery健康 | `curl http://localhost:8000/system/celery-health` |
| 测试 | `.venv/bin/pytest tests/ --ignore=tests/e2e` (769/0/0) |
| GitHub | https://github.com/05ffh/GEO-Explorer |
| sudo | 050618 |

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
| Google CSE | ❌ GCP未启用 | 已摘除, 等GCP启用后接回 |
| Brave | ❌ 无Key | 等待API Key申请 |

## 架构要点

- **adapter_registry 依赖注入**: `run_collection()` 接受 `adapter_registry` 参数
- **MockPlatformAdapter**: 9 模式 (success/rate_limited/timeout/auth_failed/等)
- **Celery fork-safe**: `os.getpid()` 进程级 HTTP client 缓存 + solo pool
- **四层数据边界**: SearchResult → Evidence → Candidate → GT
- **search_enabled**: DeepSeek/Kimi 通过 PLATFORM_KNOWLEDGE_SOURCE_POLICY 能力开关控制
- **CodeGraph**: 268 files, 3,501 nodes, 6,049 edges

## 历史 Bug (19个, 全修复)

EmailStr .local / MissingGreenlet / pipeline.py import / Wenxin遗漏 / Celery fork hang / soft_time_limit / serial→concurrent / 全局HTTP client / 内容按钮 /api前缀 / .env泄露Git历史 等

## 长期待办 (3项)

- Brave Search API Key 申请 + 接入
- Google CSE API 在 GCP 启用
- P2-1: 多轮共识 + 时间衰减
