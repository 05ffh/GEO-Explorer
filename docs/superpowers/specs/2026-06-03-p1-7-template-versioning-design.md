# P1-7: QueryTemplate 版本化 — 设计规格

**日期:** 2026-06-03
**状态:** 已确认（含审阅补齐清单）
**父项:** P1 功能增强 (P1-7)

## 动机

当前 `QueryTemplate` 模型每次直接修改字段，无版本记录。模板变更后无法追溯历史、无法回滚，正在进行的采集可能受模板修改影响。

## 设计决策

| 决策 | 选择 |
|------|------|
| 版本化触发 | **Service 层显式版本化为主**，`before_update` 降级为拦截检测 |
| 存储方式 | 影子表 `query_template_versions`，禁用 CASCADE 删除 |
| 回滚语义 | 新建版本 (change_type="rollback")，完整审计链 |
| 并发控制 | `SELECT ... FOR UPDATE` 行锁 + `expected_current_version` |
| 采集钉定 | 启动时一次性获取 `(template_id, version, version_id)`，全程使用钉定快照 |

---

## 1. 数据模型

### 1.1 新表：query_template_versions

```sql
CREATE TABLE query_template_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id UUID NOT NULL REFERENCES query_templates(id) ON DELETE RESTRICT,
    version INTEGER NOT NULL,
    organization_id UUID REFERENCES organizations(id),  -- P0-6: 租户快照

    -- versioned fields (snapshot)
    dimension VARCHAR(100) NOT NULL,
    template_text TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    question_type VARCHAR(50) DEFAULT 'brand_definition',
    brand_directed DOUBLE PRECISION DEFAULT 1.0,
    hallucination_check_enabled BOOLEAN DEFAULT TRUE,
    template_level VARCHAR(20) DEFAULT 'important',
    question_scope VARCHAR(30),
    -- P0-10: 预留扩展字段
    required_variables JSONB DEFAULT '[]'::jsonb,
    applicable_industries JSONB DEFAULT '[]'::jsonb,
    excluded_industries JSONB DEFAULT '[]'::jsonb,
    metric_eligibility JSONB DEFAULT '{}'::jsonb,

    -- version metadata
    change_type VARCHAR(20) NOT NULL,   -- create | update | rollback
    change_reason TEXT,
    rollback_from_version INTEGER,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(template_id, version)
);

CREATE INDEX ix_qtv_template ON query_template_versions(template_id);
CREATE INDEX ix_qtv_template_version ON query_template_versions(template_id, version);
CREATE INDEX ix_qtv_org ON query_template_versions(organization_id);
```

### 1.2 QueryTemplate 扩展

- 新增 `current_version: INTEGER DEFAULT 1`
- 现有字段不变

### 1.3 QueryResult 扩展

- 新增 `template_version_id: UUID REFERENCES query_template_versions(id)` (nullable)
- 现有 `template_id` 保留

### 1.4 CollectionRun 扩展（P0-7: schema_version + 最小快照）

```json
{
  "schema_version": "template_versions_snapshot_v1",
  "pinned_at": "2026-06-03T00:00:00Z",
  "templates": [
    {
      "template_id": "uuid",
      "version": 3,
      "version_id": "uuid",
      "dimension": "定义认知",
      "question_type": "brand_definition",
      "template_level": "critical",
      "question_scope": "brand_directed"
    }
  ]
}
```

### 1.5 VERSIONED_FIELDS 常量

```python
VERSIONED_FIELDS = (
    "dimension", "template_text", "priority", "question_type",
    "brand_directed", "hallucination_check_enabled",
    "template_level", "question_scope",
    "required_variables", "applicable_industries",
    "excluded_industries", "metric_eligibility",
)
```

所有影响 rendered question 和 KPI 归属的字段必须纳入此列表。

---

## 2. Service 层版本化（P0-1 核心架构）

### 2.1 新文件：`src/services/query_template_versioning.py`

废弃 `before_update` 自动插入的主逻辑，改为 Service 层显式控制。

```python
class TemplateVersioningService:
    @staticmethod
    async def create_template(
        db: AsyncSession, *, dimension, template_text, ..., created_by
    ) -> tuple[QueryTemplate, QueryTemplateVersion]:
        """创建模板 + v1 版本 (P0-2)，同一事务"""
        ...

    @staticmethod
    async def update_template(
        db: AsyncSession, *, template_id, changes: dict,
        changed_by: UUID, change_reason: str,
        expected_current_version: int | None = None,
    ) -> QueryTemplateVersion:
        """P0-3: FOR UPDATE 锁定 → 比较版本字段 → 有变更时创建新版本"""
        ...

    @staticmethod
    async def rollback_template(
        db: AsyncSession, *, template_id, target_version: int,
        reason: str, user_id: UUID,
        expected_current_version: int,
    ) -> QueryTemplateVersion:
        """P0-4: 读取目标快照 → 写回主表 → 创建 rollback 版本"""
        ...
```

### 2.2 before_update 降级为拦截检测

```python
@event.listens_for(QueryTemplate, "before_update")
def _block_direct_versioned_field_mutation(mapper, connection, target):
    """
    P0-1: 阻止绕过 Service 层的直接修改。
    如果版本化字段被改动且不在 Service 事务中 → 抛出异常。
    """
    ...
```

### 2.3 创建模板时 v1 生成（P0-2）

- `POST /api/templates` → `TemplateService.create_template()` → 原子创建 QueryTemplate + QueryTemplateVersion(v1)
- 不依赖 `after_insert` 事件
- 创建失败时不残留半截数据

### 2.4 并发控制（P0-3）

```sql
SELECT * FROM query_templates WHERE id = :id FOR UPDATE;
```

- update/rollback 必须传 `expected_current_version`
- 不匹配 → HTTP 409 + `{"detail": "Version conflict: expected 3, current 4"}`
- `UNIQUE(template_id, version)` 作为最后一道防线

### 2.5 版本创建失败阻断模板修改（P1-8）

 Service 方法内同事务：模板更新 + 版本插入。版本插入失败 → 整个事务回滚。

---

## 3. API

### 3.1 列出历史版本

```
GET /api/templates/{template_id}/versions
→ { template_id, versions: [{ version, change_type, change_reason, created_by, created_at }] }
```
- P0-6: 按 `organization_id` 过滤（租户隔离）

### 3.2 查看版本详情

```
GET /api/templates/{template_id}/versions/{version}
→ { template_id, version, ...all_versioned_fields, created_by, created_at }
```

### 3.3 版本 diff（P1-2）

```
GET /api/templates/{template_id}/versions/{from_version}/diff/{to_version}
→ { from_version, to_version, diffs: [{ field, from, to, change_type }] }
```

### 3.4 回滚（P0-4）

```
POST /api/templates/{template_id}/rollback
Body: { "version": 3, "reason": "...", "expected_current_version": 5 }

流程:
1. FOR UPDATE 锁定 template
2. 校验 expected_current_version → 不匹配 409
3. 加载 target_version 快照
4. 将 versioned 字段写回主表
5. INSERT new QueryTemplateVersion(change_type="rollback", rollback_from_version=3, change_reason, created_by)
6. UPDATE current_version = new_version
7. COMMIT
```

回滚 `change_reason` 必填，无 reason 返回 400。

---

## 4. 采集版本钉定（P0-8 原子化）

### run_collection() 改动

```
Step 1: 查询 active templates
Step 2: 对每个 template，读取 current_version
Step 3: 立即查询 query_template_versions WHERE (template_id, version) 获取 version_id
Step 4: 构造 pinned_templates: list[(template, version, version_id)]
Step 5: 后续整个 run 只使用 pinned_templates，不再读 QueryTemplate 当前值
Step 6: QueryResult 直接写入 pinned version_id
Step 7: CollectionRun.template_version_ids 写入 P0-7 结构快照
```

- 找不到 version row → TEMPLATE_VERSION_MISSING 错误 → 阻断采集

### 不变性保证

采集过程中模板被修改/回滚 → 采集继续使用启动时钉定的版本。Pipeline 分析时通过 `template_version_id` 获取当时快照。

---

## 5. 数据安全

### 5.1 删除模板不破坏历史（P0-5）

- 外键: `ON DELETE RESTRICT`
- 物理删除仅 `system_owner` 可执行，且必须无 `QueryResult.template_version_id` 引用
- 日常使用 `is_active = false` 软删除

### 5.2 历史 NULL 兼容（P0-9）

| 场景 | 规则 |
|------|------|
| 旧 QueryResult (NULL) | 报告展示 `Legacy / 未钉定`，不影响运行 |
| 新 QueryResult | 必须非 NULL，否则 `report_publishable = false`（warning） |
| 回归/验收报告 | 要求所有 QueryResult.template_version_id 非空 |

---

## 6. AuditLog 双轨（P1-3）

- `action = template.version.create / template.version.update / template.version.rollback`
- 记录 `template_id`, `version_id`, `actor`, `reason`
- 与 QueryTemplateVersion 互相对应、可交叉验证

---

## 7. Prompt Set Hash 预留（P1-5）

```python
template_set_hash = hashlib.sha256(
    ",".join(sorted(str(v["version_id"]) for v in pinned_templates)).encode()
).hexdigest()[:12]
```

写入 `CollectionRun.template_version_ids.template_set_hash`，用于报告对比和 A/B 测试。

---

## 8. Migration 计划

1. 创建 `query_template_versions` 表（含 ON DELETE RESTRICT）
2. `query_templates` 新增 `current_version INTEGER DEFAULT 1`
3. `query_results` 新增 `template_version_id` 列 (nullable)
4. `collection_runs` 新增 `template_version_ids` 列 (JSONB, nullable)
5. 为所有现有模板创建 v1 记录（change_type="create", organization_id 快照）
6. migration 幂等：再次运行时检测已有 v1 的模板，跳过
7. dry-run / apply / rollback 策略验证

不回填旧 QueryResult.template_version_id。

---

## 9. 实现顺序

| Step | 内容 |
|------|------|
| 0 | 定义 `VERSIONED_FIELDS` 常量 |
| 1 | Migration：创建表 + 列 + v1 回填 |
| 2 | 新建 `QueryTemplateVersion` 模型 |
| 3 | 新建 `TemplateVersioningService`（create / update / rollback） |
| 4 | `before_update` 拦截检测 |
| 5 | 版本 API：list / detail / diff / rollback |
| 6 | 采集钉定：pinned_templates + QueryResult.template_version_id |
| 7 | CollectionRun snapshot 写入 |
| 8 | 历史 NULL 兼容处理 |
| 9 | AuditLog 双轨 |
| 10 | 前端版本历史和回滚确认页 |
| 11 | 测试：并发、回滚、采集免疫、权限、migration |
| 12 | dry-run + 数据一致性检查 |

---

## 10. 测试清单

### Versioning Service
- `test_create_template_creates_v1`
- `test_update_template_creates_new_version`
- `test_update_template_version_insert_failure_rolls_back`
- `test_noop_update_no_version_created`

### 并发
- `test_concurrent_update_one_succeeds_one_409`
- `test_rollback_expected_current_version_mismatch_409`
- `test_version_number_no_duplicates_under_concurrency`

### 回滚
- `test_rollback_creates_new_version_with_rollback_type`
- `test_rollback_restores_versioned_fields`
- `test_rollback_requires_reason`
- `test_rollback_preserves_history`

### 采集钉定
- `test_collection_pins_template_version_at_start`
- `test_query_result_writes_template_version_id`
- `test_template_update_during_collection_no_effect`
- `test_collection_fails_when_version_row_missing`

### Legacy 兼容
- `test_old_query_result_null_version_id_displays_legacy`
- `test_new_query_result_null_version_id_warns_in_report`

### 权限与隔离
- `test_org_cannot_view_other_org_template_versions`
- `test_rollback_requires_permission`

### Migration
- `test_migration_creates_v1_for_existing_templates`
- `test_migration_idempotent`
- `test_migration_restrict_on_delete`

---

## 11. Done Definition

1. `query_template_versions` 表创建完成
2. 所有模板都有 v1
3. 模板创建/更新/回滚走 `TemplateVersioningService`
4. `current_version` 递增有 FOR UPDATE 并发保护
5. 回滚创建新版本，审计链完整
6. 新采集 `QueryResult.template_version_id` 必填
7. `CollectionRun.template_version_ids` 有 schema_version + 快照
8. 采集启动后模板变更不影响当前 run
9. 历史 NULL 展示为 legacy
10. 删除模板不破坏历史版本 (RESTRICT)
11. 组织权限隔离
12. 版本 list/detail/diff/rollback API 可用
13. 关键字段变更 reason 必填
14. AuditLog 双轨
15. 全部测试通过
16. migration dry-run / apply / rollback 已验证
