# P1-4 成本与调用监控 实现计划 v2.1

**日期:** 2026-05-30 | **审阅:** 已通过三轮专家评审

---

## 一、目标

从"看本月花了多少钱"升级为完整的 AI 调用成本治理体系：成本算得准、谁能看、什么时候告警、超预算怎么处理、日志失败不影响主流程。

---

## 二、实现任务（14 个）

### Task 1: api_usage_logs 字段补全 + Migration

扩展 35+ 字段：org/brand/user, provider/platform/model, operation_type(枚举)/module, request_id/task_id/collection_run_id/gt_candidate_id/action_theme_id/content_package_id, prompt/completion/total/cached_tokens, input/output/total_cost, billable_cost/estimated_cost/retry_cost/cost_saved, currency/original_currency/exchange_rate, pricing_version, status(success/failed/timeout/cancelled/unknown), error_code/error_message, retry_count/is_retry/billable, latency_ms, missing_usage_fields/estimation_method

### Task 2: ModelPricing 表 + 价格种子数据

DeepSeek/Kimi/豆包 各模型价格，含 effective_from/to, pricing_version, status(draft/active/deprecated), 维护权限(system_owner/admin), 变更写 AuditLog, 同一 provider+model 同一时间仅一个 active

### Task 3: 成本口径定义 + 币种策略

billable 口径：failed但平台已计费→计成本/failed确认未计费→不计/total=input+output+request/retry成本单独统计/cached按0或缓存价/cost_saved记录。MVP统一CNY展示，保留原始币种。

### Task 4: 统一 Usage Logger + 失败兜底

`src/services/usage_logger.py` — 所有外部调用统一写入。写入失败不阻断主流程，记录应用日志，连续失败达阈值生成 system alert

### Task 5: 成本统计服务

按 org/brand/platform/model/module/task 聚合，失败重试成本，单位成本，月度趋势，预计月底成本

### Task 6: 预算与告警

UsageBudget (org/brand, monthly, alert_thresholds, hard_limit) + CostAlert (8 类型, open/acknowledged/resolved, 去重：同 org+brand+type+period 仅一个 open)

### Task 7: 预算阻断策略

80%提醒/90%强提醒/100%阻断非必要高成本任务(批量采集/Content生成/多平台重复)/>120%仅 owner 放行。查看Dashboard/历史报告/成本面板不阻断。阻断/override 写 AuditLog。

### Task 8: operation_type 标准枚举

industry_classification/gt_collection/brand_geo_collection/kpi_analysis/hallucination_detection/action_generation/content_generation/report_generation/trend_attribution/embedding/search/rerank。未知写 unknown_external_call。

### Task 9: 失败无 token 估算策略

成功返token→按token算/无token有request_price→按请求计费/都无→total_cost=0,estimated_cost=true/超时未知→status=unknown

### Task 10: 成本 API

平台/组织/品牌级 cost-summary + usage-logs + alerts + budget CRUD

### Task 11: Dashboard 成本面板

本月总览(总量+估算+重试+缓存节省)/平台拆分/模块拆分/失败重试成本/预算使用率+进度条/最近告警

### Task 12: 权限 + 审计

细化权限矩阵：system_operator仅看平台运行成本(脱敏客户明细)/viewer不可看/analyst可配置/cross-org拦截。预算/价格表变更写 AuditLog。

### Task 13: 数据保留策略

MVP直查 api_usage_logs(加索引)/生产规划 daily/monthly 聚合表/明细保留180天/聚合表长期保留。

### Task 14: 测试（>=35 个）

口径/币种/价格表/预算告警去重/hard_limit/usage_logger兜底/权限边界/枚举/operation_type

---

## 三、验证标准

- [ ] Dashboard 成本面板（总量+拆分+预算+告警）
- [ ] 平台/组织/品牌三级权限隔离
- [ ] 预算阈值告警 + hard_limit 阻断
- [ ] usage_logger 失败不阻断主流程
- [ ] 144 现有 tests 继续通过
- [ ] 新增 >=35 个测试
