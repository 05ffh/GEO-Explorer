# P1-8: 历史报告重新归因 — 设计规格（修订版）

**日期:** 2026-06-03
**状态:** 已确认（含审阅补齐清单）
**父项:** P1 功能增强 (P1-8)

## 动机

P0-7 引入 4 层 claim 分类体系，但历史 CollectionRun 的 HallucinationResult 仍使用旧二分类（correct/incorrect）。P1-8 提供安全、可追溯、可回滚的历史重新归因链路。

## 设计原则（11 条硬约束）

1. **不覆盖历史** — `report_quality_summary_json` 原始值永远保留
2. **不删除批次** — 多次重归因结果共存，通过 `superseded` / `is_current` 区分
3. **批次统一管理** — 所有重归因必须有 `ReclassificationRun` 记录
4. **异步执行** — API 不阻塞，Celery task 执行
5. **dry_run 完整计算** — 实际运行 detector，只不写业务结果
6. **apply 保留旧结果** — 新 HallucinationResult 标记 `result_origin=reclassified`
7. **关联 QueryResult** — `source_query_result_id` 为必需字段
8. **版本钉定** — 记录 detector / GT / mapping / schema 版本
9. **并发锁** — 同品牌同时间范围只允许一个 running 批次
10. **权限 + AuditLog** — 所有操作可审计
11. **corrected report 新 artifact** — 不覆盖旧报告文件

---

## 1. 数据模型

### 1.1 新表：reclassification_runs

```sql
CREATE TABLE reclassification_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    brand_id UUID NOT NULL REFERENCES brands(id),

    from_date TIMESTAMPTZ,
    to_date TIMESTAMPTZ,

    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    mode VARCHAR(32) NOT NULL DEFAULT 'dry_run',
    trigger_source VARCHAR(32) NOT NULL DEFAULT 'manual',

    -- version钉定 (P0-6)
    detector_version VARCHAR(64) NOT NULL DEFAULT 'p0-7-v1',
    quality_schema_version VARCHAR(64) NOT NULL DEFAULT 'template_health_v1',
    metric_mapping_version VARCHAR(64),
    gt_schema_version VARCHAR(64),
    gt_version_strategy VARCHAR(32) NOT NULL DEFAULT 'latest_active',
    detector_config_hash VARCHAR(64),

    -- counts
    eligible_runs_count INTEGER NOT NULL DEFAULT 0,
    runs_processed INTEGER NOT NULL DEFAULT 0,
    runs_failed INTEGER NOT NULL DEFAULT 0,
    query_results_processed INTEGER NOT NULL DEFAULT 0,
    hallucination_results_created INTEGER NOT NULL DEFAULT 0,

    -- results
    classification_changes_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    sample_diffs_json JSONB,
    run_original_summaries_json JSONB,  -- P0-3: snapshot before overwrite

    -- state
    dry_run BOOLEAN NOT NULL DEFAULT false,
    official BOOLEAN NOT NULL DEFAULT false,
    superseded_by UUID,
    is_current_for_range BOOLEAN DEFAULT false,
    idempotency_key VARCHAR(255),

    -- audit
    triggered_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    reason TEXT,

    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_rr_org_brand ON reclassification_runs(organization_id, brand_id);
CREATE INDEX ix_rr_status ON reclassification_runs(status);
CREATE UNIQUE INDEX ix_rr_idempotency ON reclassification_runs(idempotency_key)
    WHERE idempotency_key IS NOT NULL;
-- P0-8: prevent concurrent active runs for same scope
CREATE UNIQUE INDEX ix_rr_active_lock ON reclassification_runs(organization_id, brand_id)
    WHERE status IN ('queued', 'running');
```

### 1.2 状态枚举

```
queued → running → completed | partial_failed | failed | cancelled
```

### 1.3 mode 枚举

```
dry_run → write_new_results → publish_corrected_summary → generate_corrected_report
```

### 1.4 CollectionRun 扩展

- `reclassified_at TIMESTAMPTZ` — 最近重归因时间
- `latest_reclassification_run_id UUID` — 当前有效批次
- `original_report_quality_summary_json JSONB` — P0-3: 首次重归因前备份原始 summary

### 1.5 HallucinationResult 扩展

- `source_query_result_id UUID NOT NULL` — P0-5: 必须追溯 QueryResult
- `source_hallucination_result_id UUID` — 如能映射旧结果
- `reclassification_of UUID` — 兼容字段
- `result_origin VARCHAR(32) NOT NULL DEFAULT 'original'` — original | reclassified
- `reclassification_run_id UUID` — 所属批次
- `is_current_reclassification BOOLEAN DEFAULT false` — P0-4: 当前有效标记

---

## 2. 异步任务架构（P0-2）

### API 行为

```
POST /api/brands/{brand_id}/reclassify
Body: { from_date, to_date, dry_run, mode, gt_version_strategy, reason, idempotency_key }

→ 1. Idempotency check (P0-8)
→ 2. Concurrent lock check (P0-8)
→ 3. Create ReclassificationRun (status=queued)
→ 4. Enqueue Celery task
→ 5. Return { reclassification_run_id, status: "queued" }
```

### 查询 API

```
GET  /api/reclassifications/{id}              — 批次详情
GET  /api/reclassifications/{id}/progress     — 进度
GET  /api/reclassifications/{id}/diff         — 差异摘要
GET  /api/reclassifications/{id}/runs         — 处理的 run 列表
POST /api/reclassifications/{id}/cancel       — 取消
POST /api/reclassifications/{id}/retry        — 重试失败
GET  /api/brands/{brand_id}/reclassifications  — 品牌历史批次列表
```

---

## 3. Task Worker 流程

### 3.1 Celery Task

```python
@celery.task(bind=True)
def run_reclassification(self, reclassification_run_id: str):
    batch = load_batch(reclassification_run_id)
    batch.status = "running"
    batch.started_at = now()

    runs = query_eligible_collection_runs(batch)
    batch.eligible_runs_count = len(runs)

    for run in runs:
        try:
            with db_transaction():      # P0-9: one run per transaction
                if batch.dry_run:
                    _dry_run_single(run, batch)
                else:
                    _apply_single(run, batch)
                batch.runs_processed += 1
        except Exception as e:
            batch.runs_failed += 1
            batch.error_summary_json[run.id] = str(e)

        batch.progress_json = build_progress(batch, runs)
        db.commit()

    batch.status = "partial_failed" if batch.runs_failed > 0 else "completed"
    batch.completed_at = now()

    if not batch.dry_run:
        set_is_current_batch(batch)
```

### 3.2 dry_run 单 run 处理（P0-7）

```
1. 加载 run 的所有 QueryResult
2. 对每个 QueryResult 执行 HallucinationDetector.detect()
3. 收集分类变化（old_verdict → new_layer）
4. 填充 sample_diffs_json（前 50 条）
5. 填充 classification_changes_json 统计
6. 不写 HallucinationResult
7. 不更新 CollectionRun
```

### 3.3 apply 单 run 处理

```
1. 保存 original_report_quality_summary_json（如果首次重归因）
2. 加载 run 的所有 QueryResult
3. 对每个 QueryResult 执行 HallucinationDetector.detect()
4. 标记旧 HallucinationResult: is_current_reclassification = false
5. 写入新 HallucinationResult(s):
   - result_origin = "reclassified"
   - source_query_result_id = QueryResult.id
   - source_hallucination_result_id = 旧结果ID（如可映射）
   - reclassification_run_id = batch.id
   - is_current_reclassification = true
6. 计算新 report_quality_summary（4层统计）
7. 写入 CollectionRun.latest_reclassified_quality_summary_json
8. 写入 CollectionRun.latest_reclassification_run_id
9. 写入 CollectionRun.reclassified_at
```

### 3.4 断点恢复（P0-9）

```
retry: 跳过 runs_processed 中已完成的 CollectionRun
       重试 runs_failed 中的 CollectionRun
       刷新 progress_json
```

---

## 4. 数据安全

### 4.1 Original vs Corrected（P0-3）

| 字段 | 用途 | 首次写入时机 |
|------|------|-------------|
| `report_quality_summary_json` | 原始采集时生成，**永不被重归因覆盖** | 采集时 |
| `original_report_quality_summary_json` | 备份（首次重归因前快照） | 首次 apply |
| `latest_reclassified_quality_summary_json` | 最新重归因结果 | 每次 apply |
| `latest_reclassification_run_id` | 当前有效批次指针 | 每次 apply |

前端展示：`original` / `corrected` 双视图。

### 4.2 批次保留（P0-4）

- 多次重归因：每次创建新 ReclassificationRun
- 旧批次 `is_current_for_range = false`
- 新批次 `is_current_for_range = true`，旧批次可设 `superseded_by`
- HallucinationResult 不删除，通过 `is_current_reclassification` 区分

### 4.3 run_original_summaries_json（P0-3）

重归因前备份每个 run 的原始 summary：
```json
{
  "<collection_run_id>": {
    "report_quality_summary_json": {...},
    "blocking_reasons_json": [...],
    "report_publishable": true
  }
}
```

---

## 5. 版本钉定（P0-6）

ReclassificationRun 记录：
- `detector_version` — HallucinationDetector 代码版本
- `detector_config_hash` — detector 配置 hash
- `gt_version_strategy` — latest_active | run_time_gt | specific
- `gt_version_ids_json` — 实际使用的 GT version ID 列表
- `quality_schema_version` — report_quality_summary schema 版本
- `metric_mapping_version` — metric_mapping.py 版本

---

## 6. 并发控制（P0-8）

- DB 约束: `UNIQUE(organization_id, brand_id) WHERE status IN ('queued', 'running')`
- API 层: `Idempotency-Key` header → 相同 key 返回同一 run_id
- task 启动时: `SELECT ... FOR UPDATE` 锁定 batch row

---

## 7. 权限（P1-2）

| 角色 | 权限 |
|------|------|
| brand analyst | dry_run only |
| brand admin | dry_run + apply |
| system_admin | 跨品牌 dry_run + apply |
| system_owner | publish corrected summary + generate corrected report |

---

## 8. Corrected Report（P0-10）

- `POST /api/reclassifications/{id}/generate-corrected-report`
- 生成新 ReportArtifact: `artifact_type = "corrected_report"`
- `correction_of_report_artifact_id` 指向原始报告
- `reclassification_run_id` 关联批次
- 不覆盖旧报告文件

---

## 9. Migration

1. 创建 `reclassification_runs` 表
2. `collection_runs` 新增: `reclassified_at`, `latest_reclassification_run_id`, `original_report_quality_summary_json`, `latest_reclassified_quality_summary_json`
3. `hallucination_results` 新增: `source_query_result_id`, `source_hallucination_result_id`, `reclassification_of`, `result_origin`, `reclassification_run_id`, `is_current_reclassification`
4. 回填: 现有 HallucinationResult 设置 `result_origin = 'original'`, `source_query_result_id = query_result_id`

---

## 10. 实现顺序

| Step | 内容 |
|------|------|
| 0 | 定义状态/mode 枚举，ReclassificationRun 模型 |
| 1 | Migration: 表 + 列 + 索引 + 约束 + 回填 |
| 2 | ReclassificationService: dry_run + apply + progress + cancel |
| 3 | Celery task: 异步执行，run 级事务，断点恢复 |
| 4 | API: trigger / status / progress / history / diff / cancel / retry / generate-report |
| 5 | Corrected report: 新 artifact，不覆盖旧报告 |
| 6 | 权限 + AuditLog + idempotency_key + 并发锁 |
| 7 | 前端: original vs corrected 视图 |
| 8 | 测试: dry_run / apply / 幂等 / 并发 / 权限 / diff / corrected report |
| 9 | 星巴克历史 run 灰度验证 |

---

## 11. 测试清单

### 模型与迁移
- `test_reclassification_runs_table_created`
- `test_reclassification_run_status_enum`
- `test_active_lock_constraint`
- `test_idempotency_key_unique`

### Dry Run
- `test_dry_run_creates_batch_no_hallucination_results`
- `test_dry_run_does_not_update_collection_run`
- `test_dry_run_returns_sample_diffs`
- `test_dry_run_records_versions`

### Apply
- `test_apply_preserves_original_hallucination_results`
- `test_apply_creates_reclassified_results_with_source_query_id`
- `test_apply_preserves_original_summary`
- `test_apply_writes_corrected_summary_separately`
- `test_apply_sets_latest_reclassification_pointers`

### 幂等/并发
- `test_idempotency_key_returns_same_run`
- `test_concurrent_same_scope_blocked`
- `test_second_reclassification_preserves_first_batch`
- `test_is_current_pointer_updates`

### 任务恢复
- `test_progress_updates`
- `test_single_run_failure_makes_partial_failed`
- `test_retry_skips_completed_runs`
- `test_cancel_marks_cancelled`

### 权限/审计
- `test_analyst_dry_run_only`
- `test_brand_admin_can_apply`
- `test_non_member_forbidden`
- `test_audit_log_written`

### Corrected Report
- `test_generate_creates_new_artifact`
- `test_artifact_links_original_and_reclassification`
- `test_original_report_not_overwritten`
