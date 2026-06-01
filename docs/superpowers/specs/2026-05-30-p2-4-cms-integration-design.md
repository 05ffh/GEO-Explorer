# GEO Explorer P2-4 CMS 集成设计文档 v2.2

**日期:** 2026-05-30
**版本:** 2.2 (Final)
**状态:** 待审阅
**变更:** v2.1→v2.2 — 数据库约束/索引/并发锁、TaskState 绑定、限流熔断/暂停、状态对账、WordPress 认证/内容转换、日志脱敏、Feature Flags 灰度、E2E/Mock Server、API 错误码/限流、审计标准字段、Sprint 优先级

---

## 1. 概述

补齐 GEO Explorer 从"生成 Content Package"到"把内容资产交付给客户发布系统"的关键链路。

**架构选型：C 方案 — Webhook 分发 + CMS Adapter 抽象并行设计**

落地顺序：Phase 1 Webhook → Phase 2 WordPress → Phase 3 Webflow/Custom CMS

---

## 2. 产品边界

### Phase 1 范围

- Content Package 标准发布模型 + PublishBatch/PublishEvent
- Publish Payload JSON Schema（机器校验）
- Webhook 分发（HMAC + SSRF + 错误分类 + 重试 + 限流熔断）
- 发布幂等（DB unique constraint + idempotency_key）
- 发布状态机（含 cancel/retry + 并发锁 + 状态对账）
- 回调安全（token + HMAC + timestamp 5min 窗口 + callback_event_id unique）
- Secret/凭据生命周期 + 日志脱敏
- CMS Adapter 抽象 + WordPress 骨架（Phase 2 完整实现）
- 健康恢复 + 自动发布边界 + 紧急暂停机制
- Feature Flags 灰度控制
- 前端 3 页面 + Mock Server + E2E
- 开发者文档 + API 错误码 + 客户可读文案

### Phase 1 不做

全量 CMS 适配、自动生产发布、媒体库上传、审批流、SEO 追踪、Custom REST 实现

---

## 3. 架构设计

### 3.1 总体链路

```
Content Package approved
        ↓ 质量门禁 → PublishEvent
创建 PublishBatch → 为每个 target 创建 PublishRequest (DB unique idempotency_key)
        ↓ 创建 TaskState, DB commit, apply_async
Worker: payload_builder → JSON Schema validate → PublishAttempt
        ↓ 发送 (HMAC + SSRF + rate limit + circuit breaker check)
更新 Attempt/Request/Batch → PublishEvent
        ↓ 客户回调 (token + HMAC + timestamp window + event_id unique)
更新状态 → CP publish_status_summary → Target health
        ↓ Reconciliation job 修复悬挂任务
```

### 3.2 模块结构

```
src/publishing/
    __init__.py
    models.py              # 7 models
    payload_builder.py     # build + JSON Schema validate + version routing + hash
    webhook.py             # HMAC + SSRF + send + retry + error classification
    delivery.py            # 统一分发 + 事务边界 + batch + 并发锁
    callbacks.py           # callback token + HMAC + timestamp window + 幂等
    security.py            # URL/IP 校验 / HMAC / 凭证加密轮换 / HTML sanitization / assets URL / redaction
    quality.py             # 质量门禁
    health.py              # target 健康评估 + 恢复
    events.py              # PublishEvent 写入
    reconciliation.py      # 状态对账定时任务
    rate_limiter.py        # 目标级限流
    circuit_breaker.py     # 目标熔断器
    monitoring.py          # 指标 + 告警
    redaction.py           # 日志脱敏工具
    feature_flags.py       # 灰度开关
    pause.py               # 紧急暂停机制
    adapters/
        base.py            # Protocol + BaseCMSAdapter
        wordpress.py       # WP Adapter (Phase 2)
    mock/
        webhook_receiver.py
        wordpress_mock.py

docs/
    schemas/
        publish_payload_2026_05.schema.json
        publish_callback_2026_05.schema.json
    webhook_integration_guide.md
```

---

## 4. 数据模型

### 4.1 PublishTarget

| 字段 | 类型 | 约束/索引 | 说明 |
|------|------|-----------|------|
| id | UUID | PK | |
| organization_id | UUID | FK, idx(org, brand) | |
| brand_id | UUID? | | 品牌级覆盖组织级 |
| name | str | | |
| target_type | str | | webhook / wordpress |
| status | str | idx(status, health_status) | active/inactive/invalid/archived |
| health_status | str | | healthy/degraded/failing/invalid/paused |
| endpoint_url | str? | | |
| auth_type | str? | | none/bearer/basic/api_key/oauth |
| auth_config_encrypted | dict? | | 加密凭据 |
| webhook_secret_hash | str? | | |
| previous_secret_hash | str? | | 24h grace period |
| secret_rotated_at | datetime? | | |
| credential_status | str | | valid/invalid/expired/unknown |
| credential_last_checked_at | datetime? | | |
| credential_error_code | str? | | |
| cms_config | dict? | | WP: site_url/category_mapping_mode/wp_* |
| payload_version | str | | 默认最新 |
| is_default | bool | partial unique(org, brand, type) where true | |
| auto_publish_on_approved | bool | default false | |
| auto_publish_max_risk_level | str | default P2 | |
| max_requests_per_minute | int? | | 目标级限流 |
| max_concurrent_requests | int? | | |
| cooldown_until | datetime? | | |
| circuit_breaker_state | str | | closed/open/half_open |
| created_by | UUID | FK | |
| verified_at | datetime? | | |
| last_success_at | datetime? | | |
| last_failed_at | datetime? | | |
| failure_count | int | | |
| consecutive_failures | int | | |
| last_health_change_at | datetime? | | |
| health_reason | str? | | |

### 4.2 PublishBatch

| 字段 | 类型 | 约束/索引 | 说明 |
|------|------|-----------|------|
| id | UUID | PK | |
| organization_id | UUID | idx(org, brand, cp) | |
| brand_id | UUID | | |
| content_package_id | UUID | | |
| trigger_type | str | | manual/content_approved/scheduled/api |
| requested_by | UUID? | | |
| status | str | idx | queued/running/partial_success/success/failed/cancelled |
| total_targets | int | | |
| success_count | int | | 并发更新用 FOR UPDATE |
| failed_count | int | | |
| cancelled_count | int | | |
| publish_request_ids | list[UUID] | | |
| idempotency_key | str | **unique** | |
| orchestration_task_state_id | str? | | Celery task_id |
| started_at | datetime? | | |
| completed_at | datetime? | | |

### 4.3 PublishRequest

| 字段 | 类型 | 约束/索引 | 说明 |
|------|------|-----------|------|
| id | UUID | PK | |
| organization_id | UUID | idx(org, brand, cp) | |
| brand_id | UUID | | |
| content_package_id | UUID | | |
| publish_target_id | UUID | idx(target, status) | |
| publish_batch_id | UUID | idx | |
| publish_action | str | | create/update/republish (Phase 1: create) |
| trigger_type | str | | |
| requested_by | UUID? | | |
| status | str | idx | 含 enqueue_failed/cancel_requested/unknown/stale/delivered_no_callback |
| idempotency_key | str | **unique** | SHA256 |
| payload_hash | str | | |
| review_required | bool | | |
| approved_for_publish | bool | | |
| force_republish | bool | | |
| republish_reason | str? | | |
| parent_publish_request_id | UUID? | | |
| task_state_id | str? | | 1:1 绑定 TaskState |
| external_id | str? | | CMS 外部 ID |
| external_edit_url | str? | | |
| external_preview_url | str? | | |
| external_public_url | str? | | |
| external_status | str? | | |
| completed_at | datetime? | | |
| error_message | str? | | |

### 4.4 PublishAttempt

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | |
| publish_request_id | UUID | FK, idx | |
| publish_target_id | UUID | FK | |
| attempt_no | int | | 从 1 递增 |
| channel | str | | webhook/wordpress |
| status | str | | sending/success/failed/retrying |
| request_payload_hash | str | | |
| payload_version | str | | |
| response_status_code | int? | | |
| response_body_summary | str? | | 脱敏+截断 |
| task_state_id | str? | | |
| external_id | str? | | |
| external_edit_url | str? | | |
| external_preview_url | str? | | |
| external_public_url | str? | | |
| external_status | str? | | |
| error_code | str? | | |
| error_category | str? | | |
| retryable | bool | | |
| error_message | str? | | 脱敏 |
| sent_at | datetime? | | |
| next_retry_at | datetime? | | |

### 4.5 PublishStatusCallback

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | |
| publish_request_id | UUID | FK, idx | |
| publish_target_id | UUID | idx | |
| callback_token_hash | str | | |
| callback_event_id | str | **unique** | 幂等键 |
| callback_timestamp | datetime | | 5min 窗口 |
| callback_signature_version | str | | |
| callback_token_expires_at | datetime | | 默认 72h |
| callback_token_used_at | datetime? | | |
| external_id | str? | | |
| external_url | str? | | |
| status | str | | received/accepted/draft_created/published/failed/rejected |
| message | str? | | |
| callback_payload | dict | | 保留 90-180 天 |
| signature_header | str? | | |
| signature_valid | bool | | |
| token_valid | bool | | |
| replay_detected | bool | | |
| processed | bool | | |
| processing_error | str? | | |
| received_at | datetime | idx | |

### 4.6 PublishEvent

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | |
| organization_id | UUID | | |
| brand_id | UUID? | | |
| content_package_id | UUID? | | |
| publish_batch_id | UUID? | idx | |
| publish_request_id | UUID? | idx | |
| publish_attempt_id | UUID? | | |
| event_type | str | idx | 见事件类型表 |
| old_status | str? | | |
| new_status | str? | | |
| message | str | | |
| metadata_json | dict | | |
| created_by | UUID? | | |

**事件类型：** `publish_requested / quality_gate_passed / quality_gate_failed / publish_enqueued / publish_enqueue_failed / publish_attempt_started / publish_attempt_failed / publish_attempt_succeeded / publish_callback_received / publish_status_updated / publish_retry_scheduled / publish_force_republish / publish_target_health_changed / publish_batch_completed / publish_paused / publish_resumed`

### 4.7 CMSFieldMapping

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | |
| publish_target_id | UUID | unique(target, type, value) idx(target, type) | |
| field_type | str | | category/tag/custom_field |
| local_value | str | | |
| external_id | str | | CMS 侧 ID |
| external_label | str? | | |

---

## 5. 数据库约束与并发锁

### 5.1 唯一约束

| 表 | 约束 | 目的 |
|----|------|------|
| PublishRequest | unique(idempotency_key) | 防重复发布 |
| PublishBatch | unique(idempotency_key) | 防重复批次 |
| PublishStatusCallback | unique(callback_event_id) | 防重复回调 |
| PublishTarget | partial unique(org, brand, type) WHERE is_default=true | 默认目标唯一 |
| CMSFieldMapping | unique(target_id, field_type, local_value) | 映射去重 |

### 5.2 并发锁

| 操作 | 锁机制 |
|------|--------|
| PublishRequest 状态转移 | SELECT ... FOR UPDATE on request row |
| PublishBatch 汇总更新 | SELECT ... FOR UPDATE on batch row |
| PublishTarget health 更新 | SELECT ... FOR UPDATE on target row |
| ContentPackage publish_status_summary | SELECT ... FOR UPDATE on cp row |
| 同一 idempotency_key 并发创建 | unique constraint + insert retry |

### 5.3 状态转移规则

- 所有状态转移通过 `transition_publish_request()` 统一入口
- 函数内部做 FOR UPDATE + 合法性校验
- 非法转移写 PublishEvent，不更新状态
- 禁止业务代码直接改 status

---

## 6. TaskState 绑定关系

| 实体 | TaskState | 说明 |
|------|-----------|------|
| PublishBatch | orchestration_task_state_id | batch 编排任务 |
| PublishRequest | task_state_id | 1:1 绑定 delivery 任务 |
| 每次 retry | 复用同一 PublishRequest，新 TaskEvent | |
| PublishAttempt | task_state_id (可选) | 关联当次尝试 |
| Callback | 不创建 TaskState | 写 PublishEvent |

---

## 7. 发布状态机

### 7.1 PublishRequest 状态

```
queued → sending → delivered → acknowledged → draft_created → published
                       ↘ failed
queued → cancelled
queued → enqueue_failed
queued → cancel_requested → cancelled (sending 时)
failed → queued (manual retry)
delivered → rejected
delivered → delivered_no_callback (token 过期仍无回调)
sending → unknown/stale (reconciliation 修复)
```

### 7.2 PublishBatch 状态

```
queued → running → success / partial_success / failed
queued → cancelled
```

### 7.3 Publish Action

| Action | Phase | 说明 |
|--------|-------|------|
| create | 1 | 新建内容 |
| update | 2 | 更新已有 |
| republish | 1 | 新 request，parent 指向原 |

### 7.4 Cancel 规则

| 状态 | 行为 |
|------|------|
| queued | → cancelled |
| sending | → cancel_requested，worker 检查后取消 |
| delivered+ | 不可 cancel |

### 7.5 Retry 规则

| 类型 | 行为 | 新 attempt_no |
|------|------|:--:|
| 自动 retry | 同一 request，新 attempt | +1 |
| 手动 retry | 同一 request，新 attempt | +1 |
| force_republish | 新 request (parent→原) | 1 |

---

## 8. 目标级限流与熔断

### 8.1 限流

| 配置 | 说明 |
|------|------|
| max_requests_per_minute | 每分钟最大请求数 |
| max_concurrent_requests | 最大并发数 |
| cooldown_until | 冷却截止时间 |

批量发布时：不同 target 可并行；同一 target 串行或受 max_concurrent 限制。

### 8.2 熔断器

```
closed → (连续失败 ≥5) → open (暂停 30min)
open → (30min 后) → half_open (允许 1 次探测)
half_open → 探测成功 → closed
half_open → 探测失败 → open
```

target 进入 open 时，关联请求标记 failed/delayed；前端提示"目标暂时熔断"。

---

## 9. 状态对账 (Reconciliation)

### 9.1 定时任务

- `reconcile_publish_requests`
- `reconcile_publish_batches`
- `reconcile_publish_targets`

### 9.2 对账规则

| 场景 | 修复 |
|------|------|
| sending > 30min 无 attempt 更新 | → unknown，需人工处理 |
| queued > 15min 未入队 | → enqueue_failed |
| batch running，所有 request 已终态 | 重算 batch status |
| delivered 且 token 过期仍无回调 | → delivered_no_callback |
| TaskState failed 但 request 非 failed | 同步状态 + PublishEvent |
| health 与 consecutive_failures 不一致 | 修复 health |

---

## 10. 紧急暂停机制

### 10.1 三级暂停

| 级别 | 作用范围 |
|------|---------|
| global_publish_pause | 全局，system_admin |
| organization_publish_pause | 单组织 |
| target_publish_pause | 单 target |

### 10.2 触发方式

- system_admin 手动暂停
- 监控告警自动触发
- target 连续失败触发 target pause
- 签名异常触发暂停

### 10.3 暂停效果

- 新 PublishRequest 不允许创建
- queued 不执行，sending 尽量停止
- delivered 等待回调，不再 retry
- 前端提示暂停原因
- AuditLog: publish_paused / publish_resumed

---

## 11. Webhook 安全

### 11.1 出站（同 v2.1）

HTTPS only, SSRF 防护, HMAC-SHA256, timeout=30s

### 11.2 回调（入站）

| 层次 | 机制 |
|------|------|
| callback_token | 一次性，72h 过期，只存 hash |
| HMAC signature | webhook secret |
| callback_event_id | DB unique，防重复 |
| timestamp | 5min 窗口，防重放 |

### 11.3 Verify Challenge

```
POST target endpoint
{"event": "publishing.target.verify", "challenge": "random", "timestamp": 123}
→ 要求 2xx 响应
→ 可选返回 challenge_token
→ 记录 verified_at
→ 失败记录 error_category
```

### 11.4 错误分类（同 v2.1）

12 种 error_category + retryable 标记

### 11.5 重试策略

5→15→30min，最多 3 次，仅 retryable=true 自动重试

### 11.6 Secret/凭据生命周期（同 v2.1）

rotate + 24h grace period + masked display + AuditLog

---

## 12. 自动发布安全边界

auto_publish_on_approved 默认 **false**。启用须满足全部：
- org 启用 + target 健康 + 风险 ≤ max_risk_level + 已配默认 target
- 高风险 (P0) 禁止自动发布
- 仅创建 draft，不发布生产

---

## 13. Publish Payload（同 v2.1 + 新增）

### 13.1 JSON Schema 机器校验

文件：`docs/schemas/publish_payload_2026_05.schema.json`、`docs/schemas/publish_callback_2026_05.schema.json`

构建后 → schema validate → 发送前再次校验

### 13.2 Assets 安全

HTTPS + SSRF + type allowlist + image 须 alt + SVG 拒绝/sanitize + assets_policy: external_reference

### 13.3 HTML 安全

body_html sanitization（去 script/iframe）+ Schema 单独字段 + WP 由 adapter 生成 script

---

## 14. WordPress Adapter（Phase 2）

### 14.1 认证

- **仅支持 Application Password**
- 要求用户至少有 `create_posts`/`edit_posts` 权限
- 不要求 `publish_posts`
- 凭据加密存储
- 验证检查 `/wp-json/wp/v2/types`、posts/pages

### 14.2 字段映射

| Payload | WordPress |
|---------|-----------|
| content.title | title |
| content.body_html (sanitized) | content |
| content.summary | excerpt |
| content.slug | slug |
| content.categories | categories (id_only + defaults) |
| content.tags | tags (id_only + defaults) |
| schema.json_ld | content 末尾 `<script type="application/ld+json">` |

### 14.3 Category/Tag Mapping

MVP: **id_only** + PublishTarget.cms_config.default_category_ids/default_tag_ids

CMSFieldMapping 缓存映射关系。

### 14.4 内容转换

- ContentPackage 保留 body_markdown
- payload_builder 生成 sanitized body_html（Markdown→HTML unified renderer → sanitization）
- WP Adapter 只用 body_html
- Schema script 由 WP Adapter 单独追加，不重复插入

### 14.5 External URL 三态

draft_created → edit_url/preview_url; published → public_url; 标注"需登录 CMS"

---

## 15. 日志脱敏 (Redaction)

### 15.1 禁止写入日志/DB summary

Authorization header / API key / Application Password / webhook secret / callback_token / 完整 body_html / 未审核 GT / 内部 prompt / 客户隐私

### 15.2 允许写入

payload_hash / cp_id / title 前 50 字 / status code / error_category / external_id / masked_url / response body 前 500 字（先脱敏）

### 15.3 工具函数

```python
redact_publish_payload(payload) → dict
redact_response_body(text) → str
mask_url(url) → str
mask_email_or_username(value) → str
```

---

## 16. Feature Flags 与灰度

| Flag | 默认 | 说明 |
|------|:----:|------|
| publishing_webhook_enabled | false | Webhook 分发 |
| publishing_wordpress_enabled | false | WP Adapter |
| publishing_auto_publish_enabled | false | 自动发布 |
| publishing_batch_enabled | false | 多目标批次 |
| publishing_assets_enabled | false | Assets 字段 |

灰度策略：system_admin → 内部测试 org → pilot 客户 → 按 plan/org 开启

前端：未开启功能不显示入口

---

## 17. API 设计

### 17.1 端点（同 v2.1 + 新增）

```
# PublishTarget
GET/POST          /api/publishing/targets
PATCH/DELETE      /api/publishing/targets/{id}
POST              /api/publishing/targets/{id}/verify
POST              /api/publishing/targets/{id}/rotate-secret

# PublishRequest
POST              /api/content-packages/{id}/publish
GET               /api/publishing/requests/{id}
GET               /api/publishing/requests
POST              /api/publishing/requests/{id}/cancel
POST              /api/publishing/requests/{id}/retry

# PublishBatch
GET               /api/publishing/batches/{id}
GET               /api/publishing/batches

# Callback
POST              /api/publishing/callbacks

# Pause (system_admin)
POST              /api/publishing/pause
POST              /api/publishing/resume

# WordPress (Phase 2)
POST              /api/publishing/targets/{id}/wordpress/test
POST              /api/content-packages/{id}/wordpress/create-draft
```

### 17.2 API 速率限制

| 端点 | 限制 |
|------|------|
| callback | 按 target_id + IP |
| verify target | 每 target 3/min |
| manual publish | 每 org 限制 |
| retry | 每 request 限制 |
| create/rotate target | 每 org 限制 |

### 17.3 统一错误码

```json
{"error_code": "PUBLISH_TARGET_INVALID", "message": "发布目标无效，请重新验证连接。", "details": {}}
```

错误码：`PUBLISH_TARGET_INVALID / UNVERIFIED / PAUSED / CONTENT_PACKAGE_NOT_APPROVED / QUALITY_FAILED / PERMISSION_DENIED / DUPLICATE_REQUEST / CALLBACK_TOKEN_INVALID / SIGNATURE_INVALID / STATUS_REGRESSION / SCHEMA_VALIDATION_FAILED / SSRF_BLOCKED / RATE_LIMITED`

### 17.4 客户可读文案

| error_category | 客户文案 |
|----------------|---------|
| auth_failed | CMS 凭据无效，请重新配置授权信息 |
| ssrf_blocked | 该 URL 不符合安全要求，不能使用内网或本地地址 |
| rate_limited | 目标系统暂时限流，系统稍后会自动重试 |
| invalid_payload | 内容格式不符合目标系统要求，请检查内容字段 |
| timeout | 目标系统响应超时，系统稍后会自动重试 |
| server_error | 目标系统暂时异常，系统稍后会自动重试 |

---

## 18. 审计日志标准字段

```
actor_user_id, actor_role, organization_id, brand_id,
resource_type, resource_id, action,
old_value_hash, new_value_hash,
ip_address_hash, user_agent, request_id, created_at
```

凭据变更只记录 hash/metadata，不记录明文。

---

## 19. 前端页面（同 v2.1 + 新增）

- **发布目标管理页** — 含 health 标记、验证结果、熔断状态、暂停状态
- **Content Package 发布面板** — 多目标选择、发布预览、timeline、状态区分（delivered ≠ published）、外部链接三态
- **发布历史页** — 筛选/分页/导出、回调状态区分、暂停提示

---

## 20. 报告语言约束

- 允许："内容已推送为草稿"、"N 个目标中 M 个成功"
- 允许："后续需通过下一轮 AI 诊断观察目标 KPI"
- 禁止："发布后已修复 AI 认知问题"

---

## 21. Sprint 实施优先级

### Sprint 1：发布核心骨架
数据模型 + migration、Payload Builder、质量门禁、PublishBatch/Request/Event、状态机 + 并发锁、基础 RBAC、基础 API

### Sprint 2：Webhook 安全分发
Webhook target、HMAC、SSRF、send/attempt、retry、callback + token + timestamp 窗口、idempotency (DB unique)、TaskState 绑定、日志脱敏

### Sprint 3：前端与可观测
目标管理、发布预览/timeline、发布历史、限流熔断、暂停机制、对账任务、Feature Flags、监控告警、API 限流/错误码、客户文案

### Sprint 4：WordPress Draft Adapter
Application Password、字段映射、category/tag id_only、external URLs、schema html_block、Markdown→HTML、WordPress 测试、Mock Server

---

## 22. Mock Server & E2E

### Mock Server
- Webhook Receiver Mock（接收 + HMAC 验证 + callback 回传）
- WordPress Mock（/wp/v2/posts, /wp/v2/pages）
- `docker-compose webhook-receiver` / `mock_wordpress.py`

### E2E 场景 (8)
1. Webhook 成功发布 + callback acknowledged
2. Webhook 5xx 自动重试后成功
3. 同一 CP 多目标发布，部分成功部分失败
4. 重复点击发布按钮只创建一个 PublishRequest
5. WordPress 创建 draft 并返回 edit_url
6. invalid target 阻止发布
7. 跨组织用户无法发布
8. global pause 后无法创建发布请求

---

## 23. 测试计划（90+ tests, 分层）

| 层级 | 覆盖 |
|------|------|
| **Unit** | 安全 (SSRF/HMAC/token)、payload、状态机、字段映射、redaction |
| **Integration** | Webhook mock、callback mock、WordPress mock、TaskState、reconciliation |
| **E2E** | 8 场景完整链路 |
| **Security** | SSRF、HMAC replay、token expiry、cross-org isolation |
| **Regression** | schema compatibility、idempotency、backward compat |

### 新增测试类别 (v2.2)

**DB 约束与并发 (5)**
- idempotency_key unique constraint
- callback_event_id unique constraint
- default target unique per scope/type
- concurrent publish creates single request
- concurrent batch status update safe

**TaskState 与对账 (5)**
- publish_request has task_state
- retry creates new attempt + task_event
- reconcile sending timeout → failed
- reconcile batch recomputes status
- delivered_no_callback after token expiry

**限流与熔断 (5)**
- target rate limit blocks excess
- circuit breaker opens after failures
- half_open probe success closes circuit
- global pause blocks new requests
- org pause blocks org requests

**WordPress 认证与转换 (5)**
- application password validation
- requires create_posts permission
- markdown→HTML renderer
- schema script not duplicated on update
- publish permission not required for draft

**日志脱敏 (5)**
- authorization header redacted
- callback_token not logged
- body_html not in response summary
- url masking
- response body truncated and redacted

**Feature Flags (4)**
- webhook flag hides frontend
- wordpress flag blocks API
- auto_publish flag default off
- custom_rest returns 501

**E2E (8)** — 见上文

---

## 24. 任务清单（28 tasks, 4 Sprints）

| # | Sprint | 任务 |
|---|:------:|------|
| 1 | 1 | 数据模型与 Migration（含 DB 约束/索引） |
| 2 | 1 | Publish Payload Builder + JSON Schema 校验 |
| 3 | 1 | 质量门禁 |
| 4 | 1 | PublishBatch / PublishRequest / PublishEvent |
| 5 | 1 | 状态机 + 并发锁（SELECT FOR UPDATE） |
| 6 | 1 | 基础 RBAC + 跨组织隔离 |
| 7 | 1 | 基础 API |
| 8 | 2 | Webhook Target 管理 |
| 9 | 2 | HMAC + SSRF + Send Attempt |
| 10 | 2 | Retry + 错误分类 |
| 11 | 2 | Callback + Token + Timestamp 窗口 |
| 12 | 2 | 发布幂等 + DB Unique Constraints |
| 13 | 2 | TaskState 绑定 |
| 14 | 2 | 日志脱敏 |
| 15 | 3 | Target 健康恢复 + Auto Publish 边界 |
| 16 | 3 | 限流 + 熔断器 |
| 17 | 3 | 暂停机制 (global/org/target) |
| 18 | 3 | 对账任务 (Reconciliation) |
| 19 | 3 | Feature Flags |
| 20 | 3 | 监控告警 + API 限流 + 错误码 + 客户文案 |
| 21 | 3 | 审计日志标准字段 |
| 22 | 3 | 前端：Target 管理 + 发布预览/Timeline + 发布历史 |
| 23 | 4 | WordPress Application Password + 权限最小化 |
| 24 | 4 | WordPress 字段映射 + Category/Tag id_only |
| 25 | 4 | Markdown→HTML Renderer + Sanitization + Schema 去重 |
| 26 | 4 | External URL 三态 |
| 27 | 4 | Mock Server (Webhook + WordPress) |
| 28 | 4 | 测试 (90+ Unit/Integration/E2E/Security/Regression) |

---

## 25. 验收标准

1. Webhook target 可创建、验证 (challenge)、停用、轮换 secret
2. PublishBatch 支持多目标发布，并发安全 (FOR UPDATE)
3. idempotency_key DB unique 防重复；force_republish 需 admin
4. Payload 经 JSON Schema 机器校验
5. Webhook HMAC + SSRF (URL + assets) + 错误分类 + 限流重试
6. 回调 token + HMAC + timestamp 5min + event_id unique + 防回退
7. PublishEvent 完整 timeline，前端可展示
8. Target health: degraded/failing → 成功恢复；invalid → verify 恢复
9. 熔断器: closed→open(5)→half_open(30min)→探测
10. 紧急暂停: global/org/target 三级
11. 对账任务修复悬挂/不一致状态
12. WordPress: Application Password, id_only, draft, external_urls, schema 去重
13. body_html sanitization + assets URL SSRF + 日志脱敏
14. Feature Flags 控制灰度，未开启不显示前端入口
15. cancel 规则正确；retry 类型区分清晰
16. Target 默认规则 + 软删除 + cross-org 隔离
17. API 限流 + 统一错误码 + 客户可读文案
18. AuditLog 标准字段 + secret/凭据 masked
19. 报告中禁止写"发布后已修复 AI 认知问题"
20. 开发者文档 (含示例代码 + JSON Schema + Mock)
21. 90+ tests (Unit/Integration/E2E/Security/Regression) + 334 existing → 424+

---

*设计文档 v2.2 (Final) — 2026-05-30*
