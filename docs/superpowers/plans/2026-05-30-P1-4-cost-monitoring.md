# P1-4 成本与调用监控 实现计划

**日期:** 2026-05-30 | **状态:** Plan | **当前完成度:** 0%
**依赖:** api_usage_logs 模型已存在

---

## 一、目标

让系统管理员能看到 API 调用量、Token 消耗、费用估算和平台拆分，避免成本失控。

---

## 二、当前状态

- `api_usage_logs` 表已存在（prompt_tokens / completion_tokens / cost / status）
- 但 Dashboard 没有成本面板，也没有成本告警

---

## 三、实现任务

### Task 1: 成本统计服务

**文件:** `src/services/cost_service.py`（新建）

- 查询本组织/全部组织的 API 使用统计
- 聚合：本月调用次数/Token/费用/各平台拆分/失败重试成本/预算剩余

### Task 2: Dashboard 成本面板

**文件:** `src/templates/dashboard/index.html`（扩展）

新增"成本与调用"卡片：本月调用次数 + Token 消耗 + 费用估算 + 平台拆分 + 成本趋势迷你图

### Task 3: 平台级成本 API

**文件:** `src/api/cost.py`（新建）

- `GET /api/platform/cost-summary` — system_owner/admin 查看全平台成本
- `GET /api/organizations/{id}/cost-summary` — org 级成本

### Task 4: 成本记录接入

**文件:** 所有 AI adapter 调用点

确保每次 API 调用写入 api_usage_logs（prompt_tokens / completion_tokens / cost）

### Task 5: 测试

---

## 四、验证标准

- [ ] Dashboard 展示本月成本概览
- [ ] system_owner 可查看全平台成本
- [ ] 144 现有 tests 继续通过
- [ ] 新增 >=8 个测试
