# P1-3 权限与审核流 实现计划 v2

**日期:** 2026-05-30 | **状态:** Plan | **审阅:** 已通过方向评审，v2 修正全部 P0/P1
**当前完成度:** 50% → 目标 100%

---

## 一、目标

从"定义了 6 个角色 + 前端按钮隐藏"升级为"permission-based 后端强制权限 + before/after 审计 + 组织隔离 + 状态业务条件守卫 + 字段级追踪"。

核心原则：
```text
前端权限 = 用户体验优化
后端权限 = 安全边界
审计日志 = 合规追溯
```

---

## 二、修正清单（v1 → v2）

| # | 问题 | v1 做法 | v2 修正 |
|---|------|---------|---------|
| P0-1 | 组织隔离 | 无 | 所有资源查询先校验 `organization_id == user.organization_id`，跨组织返回 404 |
| P0-2 | 审计事务 | 独立 `db.commit()` | `db.add(log)` 参与同一事务，外层统一 commit/rollback |
| P0-3 | 审计结构 | 仅 `detail: dict` | 增加 `before_json` / `after_json` / `reason` / `request_id` |
| P0-4 | 枚举 | 自由文本 | `AuditAction` / `AuditTargetType` 枚举 |
| P0-5 | 状态条件 | 仅 TRANSITION_GUARDS | 两层：Role Guard（角色）+ Condition Guard（业务条件） |
| P0-6 | 内容审批 | 仅 legal_reviewer/admin | 按风险等级：low→editor可审 / high→legal+admin |
| P0-7 | GT 审计 | candidate 级 | 字段级：gt_field_accept/edit/delete/mark_uncertain/resolve_conflict |
| P0-8 | 幻觉裁决 | confirmed/dismissed | 7 种：confirmed_error/dismissed/partial/gt_is_wrong/outdated/needs_evidence/low_risk |
| P0-9 | 报告审计 | 无范围 | report_type + included_sections + export_format |
| P0-10 | 用户管理 | 缺失 | 成员列表 + 角色变更 + 安全规则 |

---

## 三、实现任务

### Task 1: AuditLog 模型 + Permission Map + 枚举

**文件:** `src/models/audit_log.py`（新建）+ Migration

```python
import enum

class AuditAction(str, enum.Enum):
    GT_FIELD_ACCEPT = "gt_field_accept"
    GT_FIELD_EDIT = "gt_field_edit"
    GT_FIELD_DELETE = "gt_field_delete"
    GT_FIELD_UNCERTAIN = "gt_field_mark_uncertain"
    GT_PROMOTE = "gt_promote"
    HALLUCINATION_REVIEW = "hallucination_review"
    ACTION_TRANSITION = "action_transition"
    CONTENT_APPROVE = "content_approve"
    CONTENT_REJECT = "content_reject"
    CONTENT_PUBLISH = "content_publish"
    REPORT_EXPORT = "report_export"
    ROLE_CHANGE = "role_change"
    PERMISSION_DENIED = "permission_denied"

class AuditTargetType(str, enum.Enum):
    GT_CANDIDATE = "gt_candidate"
    GT_FIELD = "gt_field"
    HALLUCINATION = "hallucination"
    ACTION_THEME = "action_theme"
    CONTENT_PACKAGE = "content_package"
    REPORT = "report"
    BRAND = "brand"
    USER = "user"


class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_logs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    brand_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("brands.id"), nullable=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    user_name: Mapped[str] = mapped_column(String(255), default="")
    user_role: Mapped[str] = mapped_column(String(50), default="")
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    before_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    after_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")
    request_id: Mapped[str] = mapped_column(String(100), default="", index=True)
    ip_address: Mapped[str] = mapped_column(String(50), default="")
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
```

**文件:** `src/auth/permissions.py`（新建）

```python
PERMISSIONS = {
    "gt.review": {"roles": ["gt_reviewer", "admin"]},
    "gt.promote": {"roles": ["gt_reviewer", "admin"]},
    "hallucination.review": {"roles": ["analyst", "gt_reviewer", "admin"]},
    "action.transition": {"roles": ["analyst", "content_editor", "admin"]},
    "content.approve.low": {"roles": ["content_editor", "legal_reviewer", "admin"]},
    "content.approve.medium": {"roles": ["legal_reviewer", "admin"]},
    "content.approve.high": {"roles": ["legal_reviewer", "admin"]},
    "content.publish": {"roles": ["content_editor", "admin"]},
    "report.export.summary": {"roles": ["analyst", "admin"]},
    "report.export.full": {"roles": ["admin"]},
    "audit.view.org": {"roles": ["admin"]},
    "user.manage": {"roles": ["admin"]},
}

def has_permission(user_role: str, permission: str) -> bool:
    allowed = PERMISSIONS.get(permission, {}).get("roles", [])
    return user_role in allowed
```

---

### Task 2: 审计日志写入工具（同一事务）

**文件:** `src/services/audit.py`（新建）

```python
async def add_audit_log(db, user, action: str, target_type: str, target_id: str,
                        before: dict = None, after: dict = None,
                        detail: dict = None, reason: str = "",
                        brand_id: str = None, request: Request = None):
    """Add audit log to current transaction — do NOT commit here."""
    log = AuditLog(
        organization_id=user.organization_id,
        brand_id=brand_id,
        user_id=user.id, user_name=user.name or "", user_role=user.role or "",
        action=action, target_type=target_type, target_id=str(target_id),
        before_json=before or {}, after_json=after or {},
        detail=detail or {}, reason=reason,
        request_id=getattr(request, "headers", {}).get("x-request-id", "") if request else "",
        ip_address=request.client.host if request and request.client else "",
        user_agent=request.headers.get("user-agent", "") if request else "",
    )
    db.add(log)
    return log
```

业务端点调用模式：
```python
# 业务操作
theme.status = "confirmed"
await add_audit_log(db, user, AuditAction.ACTION_TRANSITION, AuditTargetType.ACTION_THEME,
                    theme.id, before={"status": "detected"}, after={"status": "confirmed"})
# 统一提交
await db.commit()
```

---

### Task 3: RBAC 依赖注入 + 资源归属查询

**文件:** `src/api/deps.py`（扩展）

```python
def require_permission(permission: str):
    """FastAPI dependency: check permission, raise 403 if denied."""
    async def checker(user: User = Depends(get_current_user)):
        from src.auth.permissions import has_permission
        if not has_permission(user.role or "", permission):
            raise HTTPException(status_code=403, detail={
                "error": "permission_denied",
                "required": permission,
                "user_role": user.role,
                "message": "你没有此操作的权限",
            })
        return user
    return checker


async def get_org_resource_or_404(model, resource_id, user, db):
    """Fetch resource, verify org ownership. Returns 404 (not 403) for cross-org."""
    result = await db.execute(select(model).where(model.id == resource_id))
    resource = result.scalar_one_or_none()
    if not resource or resource.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Not found")
    return resource
```

---

### Task 4: API 端点权限 + 审计加固

逐端点改造。模式：`Depends(require_permission("xxx"))` + `add_audit_log` + 业务条件守卫。

**覆盖清单：**

| 端点 | 权限 | 审计 action | 业务条件 |
|------|------|------------|---------|
| `POST /api/gt-candidates/{id}/review` | `gt.review` | `gt_field_accept/edit/delete/uncertain` | 字段级 before/after 值 |
| `POST /api/gt-candidates/{id}/promote` | `gt.promote` | `gt_promote` | 高风险字段已审核 + 证据充足 |
| `POST /api/hallucinations/{id}/review` | `hallucination.review` | `hallucination_review` | verdict + needs_human_review |
| `POST /api/action-themes/{id}/transition` | `action.transition` | `action_transition` | Role Guard + Condition Guard |
| `POST /api/content-packages/{id}/approve` | `content.approve.{risk_level}` | `content_approve` | 按 low/medium/high |
| `POST /api/content-packages/{id}/reject` | `content.approve.{risk_level}` | `content_reject` | 需要 rejection reason |
| `POST /api/content-packages/{id}/mark-published` | `content.publish` | `content_publish` | 需要 publish_url |
| `POST /api/dashboard/brands/{id}/reports/generate` | `report.export.summary` | `report_export` | 记录 report_type + format |

---

### Task 5: Action 状态转移条件守卫

**文件:** `src/view_models/action.py`（扩展）

```python
def validate_transition_conditions(theme: ActionTheme, to_status: str, payload: dict) -> list[str]:
    """Return list of blocking reasons, or empty list if OK."""
    issues = []
    if to_status == "approved" and theme.status == "content_ready":
        if not theme.action_plan_ids:
            issues.append("缺少关联的 Content Package")
    if to_status == "published_marked":
        if not payload.get("publish_url"):
            issues.append("必须填写 publish_url")
    if to_status == "verified":
        if theme.status != "verification_pending":
            issues.append("必须先进入 verification_pending 状态")
    return issues
```

---

### Task 6: 审计日志查询 API

**文件:** `src/api/audit.py`（新建）

```text
GET /api/audit-logs?brand_id=&action=&user_id=&page=&page_size=
```

- admin/owner 查看组织级
- 支持筛选：action, target_type, user_id, brand_id, date_from, date_to
- 分页 + 排序（按时间倒序）
- 结果不含其他组织的日志（organization_id 隔离）

---

### Task 7: 测试（25+ 个）

**文件:** `tests/test_permissions.py`（新建）

```text
# 权限
test_viewer_cannot_review_gt
test_viewer_cannot_transition_action
test_content_editor_cannot_approve_high_risk
test_analyst_cannot_promote_gt

# 组织隔离
test_cross_org_resource_returns_404
test_cannot_access_other_org_action_theme
test_cannot_query_other_org_audit_logs

# 审计
test_gt_review_writes_audit_log
test_gt_promote_logs_before_after
test_action_transition_logs_from_to_status
test_audit_in_same_transaction

# 状态守卫
test_publish_requires_url
test_high_risk_requires_legal_reviewer

# 审计查询
test_admin_can_query_audit_logs
test_viewer_cannot_query_org_audit_logs
```

---

## 四、验证标准

- [ ] Viewer 不能审核 GT → HTTP 403
- [ ] 跨组织访问资源 → HTTP 404
- [ ] Content Editor 不能 approve 高风险内容
- [ ] GT Promote 后审计日志含 before/after 快照
- [ ] 审计日志与业务在同一事务中
- [ ] 所有 POST 操作有审计
- [ ] 审计 API 有组织隔离
- [ ] 现有 113 tests 继续通过
- [ ] 新增 >=25 个测试
