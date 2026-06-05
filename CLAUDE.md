# GEO Explorer

品牌 AI 可见度监测与优化平台。Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Celery+Redis / PostgreSQL 16 / Jinja2+HTMX。

**全程「工程师」模式推进**（Define→Plan→Build→Verify→Review→Ship），不跳过任何阶段。

## 项目状态

**全部完成。631 tests (0 failures)。集成审计通过，完整管道跑通。GitHub: https://github.com/05ffh/GEO-Explorer**

Phase A + P0 7-10 + P1 1-10 + P2 1-4 + 前端架构补齐 + ClaimNature v2 + 5模块前端补齐 + 集成审计。

完整链路 (已验证端到端):
```
GT采集(S/A/B/C/D) → GT审核 → 品牌GEO采集 → 模板健康前置门槛 → 模板版本钉定
→ 5KPI + 5扩展KPI → 4层幻觉分类 → ClaimNature v2
→ 多证据GT → 行业KPI权重 → 样本充分度
→ Action Theme → Content Package → 报告质量Summary → Go/No-Go
→ 三格式报告 → 历史重归因 → 人审闭环
```

**ClaimNature v2**: Accuracy 77.0%, UNKNOWN 20.0%, SPECULATION recall 85.7%, Macro F1 0.696

## 前端补齐流程

spec → 桌面审阅 → 补齐清单 → 吸收 → Build → 验证 (可跳过 Plan)。TDD 铁律。

## 设计系统

Data-Dense Dashboard, #1E40AF/#3B82F6/#F59E0B, Fira Code+Fira Sans, Jinja2+HTMX+Tailwind CDN+Chart.js+Heroicons

## 关键路径

- 项目: `/home/ffh/explore geo/`, symlink `/home/ffh/geo-explorer`
- API: http://localhost:8000/login
- DB: Docker `exploregeo-db-1:5432` / test `exploregeo-test_db-1:5433`
- Redis: systemd `geo-redis:6379`
- Systemd: `geo-redis`, `geo-celery`, `geo-api`
- sudo: 050618

## 历史 Bug 清单 (已全部修复)

| Bug | 文件 | 影响 |
|-----|------|------|
| `_page_context` current_page 关键字重复 → TypeError 500 | `main.py` | SaaS/Queue/Publishing 全挂 |
| Jinja2 `vm.xxx` dict 方法冲突 (queue_monitor + publishing) | 2 个模板 | 页面崩溃 |
| `add_audit_log(None)` → Celery DLQ 崩溃 | `services/audit.py` | 任务失败无法追踪 |
| `_PreflightResult(status=...)` 参数名不匹配 | `collector/engine.py` | 全部模板误判 invalid |
| `_build_template_health_report` 不接受 QueryTemplate | `collector/engine.py` | Preflight 误报 |
| Dashboard `collection-runs` → 应为 `collections` | `dashboard/index.html` | 按钮 404 |
| `deliver_customer_reports` 不存在 | `main.py` | 报告生成 API 500 |
| `sum(status=="success")` SQL 表达式错误 | `run_detail.py` | Run 详情页 500 |

## 长期待办

- Wenxin API Key 续期
- GT 来源升级 C→S/A/B
- Doubao/Kimi 限流缓解
