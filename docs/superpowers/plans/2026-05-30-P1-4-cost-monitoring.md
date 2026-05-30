# P1-4 成本与调用监控 实现计划 v2

**日期:** 2026-05-30 | **状态:** Plan | **审阅:** 已通过方向评审，v2 修正全部 P0/P1

---

## 一、目标

从"看本月花了多少钱"升级为"AI 调用成本治理体系"：知道钱花在哪（哪个组织/品牌/模型/模块/任务）、哪次失败重试浪费了成本、预算快用完时提醒和阻断。

---

## 二、修正清单

| P0 | v1 | v2 |
|----|-----|-----|
| P0-1 | 仅 prompt/completion_tokens/cost | 扩展 30+ 字段（org/brand/model/operation_type/retry/...） |
| P0-2 | 成本硬编码 | ModelPricing 表 + pricing_version |
| P0-3 | 仅按组织统计 | 按组织/品牌/平台/模型/模块/任务归因 |
| P0-4 | "预算剩余"一句带过 | UsageBudget 模型 + 阈值(80/90/100%) + hard_limit |
| P0-5 | 无告警 | CostAlert 模型 + 6 种告警类型 |
| P0-6 | admin 模糊 | 平台级/组织级/品牌级严格权限边界 |
| P0-7 | 提到但未细化 | status/failed/retry_count/is_retry/billable 字段 |
| P0-8 | 仅 AI adapter | 统一 usage_logger 覆盖所有外部调用 |
| P0-9 | 无绑定 | collection_run_id/gt_candidate_id/action_theme_id/content_package_id |
| P0-10 | >=8 测试 | >=25 测试 |

---

## 三、实现任务（9 个）

### Task 1: api_usage_logs 字段补全 + Migration

扩展字段：organization_id, brand_id, user_id, provider, platform, model_name, model_version, operation_type, module_name, request_id, task_id, collection_run_id, gt_candidate_id, action_theme_id, content_package_id, total_tokens, cached_tokens, input_cost, output_cost, total_cost, currency, pricing_version, estimated_cost, status, error_code, error_message, retry_count, is_retry, retry_of_log_id, billable, latency_ms

### Task 2: ModelPricing 表 + 价格种子数据

DeepSeek/Kimi/豆包 各模型 input/output price per 1k tokens，含 effective_from/effective_to/pricing_version

### Task 3: 统一 Usage Logger

`src/services/usage_logger.py` — 所有 AI/search/embedding/content/report 调用统一写日志，失败也记录

### Task 4: 成本统计服务

`src/services/cost_service.py` — 按 org/brand/platform/model/module/task 聚合，失败重试成本，单位成本，月度趋势

### Task 5: 预算与告警

UsageBudget 模型（org/brand 级，period=monthly, alert_thresholds, hard_limit）+ CostAlert 模型（6 种告警类型）

### Task 6: 成本 API

平台级/组织级/品牌级 cost-summary + usage-logs 查询 + alerts + budget CRUD

### Task 7: Dashboard 成本面板

本月总览/平台拆分/模块拆分/失败重试成本/预算使用率/最近告警

### Task 8: 权限 + 审计

系统级/组织级/品牌级严格权限，预算变更写 AuditLog，跨组织查询拦截

### Task 9: 测试（>=25 个）

usage log / 成本计算 / 聚合 / 权限 / 预算告警 / Dashboard API

---

## 四、验证标准

- [ ] Dashboard 展示成本概览（总量+平台拆分+模块拆分+预算+告警）
- [ ] system_owner 可查看全平台成本
- [ ] 组织 owner/admin 只能看本组织
- [ ] 144 现有 tests 继续通过
- [ ] 新增 >=25 个测试
