# P1-3 权限与审核流 实现计划 v2.1

**日期:** 2026-05-30 | **状态:** Plan | **审阅:** 已通过三轮专家评审
**当前完成度:** 50% → 目标 100%

---

## 一、目标

从"定义了 6 个角色 + 前端按钮隐藏"升级为"permission-based 后端强制权限 + before/after 审计 + 组织隔离 + 状态业务条件守卫 + 字段级追踪 + 审计防篡改"。

核心原则：
```text
前端权限 = 用户体验优化
后端权限 = 安全边界
审计日志 = 合规追溯（append-only, 可脱敏）
```

---

## 二、角色体系（统一为 7 角色）

| 角色 | 说明 |
|------|------|
| owner | 组织拥有者（管理账单、转移所有权、管理 admin） |
| admin | 组织管理员（管理成员、权限、品牌配置） |
| analyst | 数据分析师（查看 KPI + 触发采集 + 复核幻觉） |
| gt_reviewer | GT 审核员（字段级审核 + Promote） |
| content_editor | 内容编辑（生成内容 + 标记发布） |
| legal_reviewer | 法务审核（审批高风险内容） |
| viewer | 只读（查看 Dashboard 和报告） |

安全规则：
- 每个 org 至少 1 个 owner
- admin 不能修改/降级/移除 owner
- 不能移除/降级最后一个 admin（如无 owner）
- 用户不能把自己降级为导致组织无管理员的状态

---

## 三、权限矩阵

| 功能 | viewer | analyst | gt_reviewer | content_editor | legal_reviewer | admin | owner |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 查看 Dashboard | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 触发采集 | - | ✓ | - | - | - | ✓ | ✓ |
| 审核 GT 字段 | - | - | ✓ | - | - | ✓ | ✓ |
| Promote GT | - | - | ✓ | - | - | ✓ | ✓ |
| 复核幻觉 | - | ✓ | ✓ | - | - | ✓ | ✓ |
| 确认 Action | - | ✓ | - | - | - | ✓ | ✓ |
| 生成内容 | - | - | - | ✓ | - | ✓ | ✓ |
| 审核高风险内容 | - | - | - | - | ✓ | ✓ | ✓ |
| 标记发布 | - | - | - | ✓ | - | ✓ | ✓ |
| 导出摘要报告 | - | ✓ | - | - | - | ✓ | ✓ |
| 导出完整报告 | - | - | - | - | - | ✓ | ✓ |
| 查看组织审计 | - | - | - | - | - | ✓ | ✓ |
| 管理成员 | - | - | - | - | - | ✓ | ✓ |
| 转移所有权 | - | - | - | - | - | - | ✓ |

---

## 四、实现任务

### Task 1: AuditLog 模型 + 枚举 + Permission Map

**文件:** `src/models/audit_log.py` + Migration

```python
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
    USER_INVITE = "user_invite"
    USER_ROLE_CHANGE = "user_role_change"
    USER_DISABLE = "user_disable"
    USER_REMOVE = "user_remove"
    PERMISSION_DENIED = "permission_denied"
```

AuditLog 包含字段：`organization_id`, `brand_id`, `user_id`, `user_name`, `user_role`, `action`, `target_type`, `target_id`, `before_json`, `after_json`, `detail`, `reason`, `result`(success/denied/blocked/failed), `error_code`, `error_message`, `request_id`, `ip_address`, `user_agent`, `created_at`。

审计策略：
- Append-only：不提供 update/delete API
- 保留至少 180 天
- 查询 API 对非 admin 脱敏 detail 字段

**文件:** `src/auth/permissions.py`

```python
PERMISSIONS = {
    "gt.review":      ["gt_reviewer", "admin", "owner"],
    "gt.promote":     ["gt_reviewer", "admin", "owner"],
    "hallucination.review": ["analyst", "gt_reviewer", "admin", "owner"],
    "action.transition":    ["analyst", "content_editor", "admin", "owner"],
    "content.approve.low":  ["content_editor", "legal_reviewer", "admin", "owner"],
    "content.approve.medium": ["legal_reviewer", "admin", "owner"],
    "content.approve.high": ["legal_reviewer", "admin", "owner"],
    "content.approve.legal_sensitive": ["legal_reviewer", "admin", "owner"],  # P2: 双人确认
    "content.publish":  ["content_editor", "admin", "owner"],
    "report.export.summary": ["analyst", "admin", "owner"],
    "report.export.full":    ["admin", "owner"],
    "audit.view.org":   ["admin", "owner"],
    "user.view":        ["admin", "owner"],
    "user.invite":      ["admin", "owner"],
    "user.role_change": ["admin", "owner"],
    "user.disable":     ["admin", "owner"],
    "user.remove":      ["admin", "owner"],
    "user.remove_admin": ["owner"],
}
```

---

### Task 2: 审计日志写入工具 + RequestIdMiddleware

**文件:** `src/services/audit.py`

```python
async def add_audit_log(db, user, action, target_type, target_id,
                        before=None, after=None, detail=None, reason="",
                        result="success", error_code="", error_message="",
                        brand_id=None, request=None):
    """Add audit log to current transaction — do NOT commit here (P0-2)."""
    log = AuditLog(
        organization_id=user.organization_id, brand_id=brand_id,
        user_id=user.id, user_name=user.name or "", user_role=user.role or "",
        action=action, target_type=target_type, target_id=str(target_id),
        before_json=before or {}, after_json=after or {},
        detail=detail or {}, reason=reason,
        result=result, error_code=error_code, error_message=error_message,
        request_id=request.state.request_id if request and hasattr(request.state, 'request_id') else "",
        ip_address=request.client.host if request and request.client else "",
        user_agent=request.headers.get("user-agent", "") if request else "",
    )
    db.add(log)
    return log
```

**文件:** `src/middleware/request_id.py`

```python
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

---

### Task 3: RBAC 依赖注入 + 专用资源归属函数

**文件:** `src/api/deps.py`（扩展）

```python
def require_permission(permission: str):
    """FastAPI dependency: return 403 with structured error if denied."""
    async def checker(user: User = Depends(get_current_user)):
        from src.auth.permissions import PERMISSIONS
        allowed = PERMISSIONS.get(permission, {}).get("roles", []) if isinstance(PERMISSIONS.get(permission), dict) else PERMISSIONS.get(permission, [])
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail={
                "error": "permission_denied", "required": permission,
                "user_role": user.role, "message": "你没有此操作的权限",
            })
        return user
    return checker

# 专用资源归属函数（P0-8：不依赖通用 model.organization_id 假设）
async def get_org_brand_or_404(brand_id, user, db): ...       # Brand.organization_id
async def get_org_gt_candidate_or_404(cid, user, db): ...      # GroundTruthCandidate.organization_id
async def get_org_action_theme_or_404(tid, user, db): ...      # ActionTheme.organization_id
async def get_org_content_package_or_404(pid, user, db): ...   # ContentPackage.organization_id
async def get_org_hallucination_or_404(hid, user, db): ...     # HallucinationResult → brand → org
async def get_org_audit_log_or_404(aid, user, db): ...         # AuditLog.organization_id
# 每个函数内部做 organization_id 校验，跨组织返回 404
```

---

### Task 4: 状态守卫细化 — ActionTheme + ContentPackage

**ActionTheme 状态流转 + 条件：**

| 流转 | 角色 | 业务条件 |
|------|------|---------|
| detected → confirmed | analyst/admin/owner | 有证据链 |
| confirmed → content_generating | content_editor/admin/owner | 有 target KPI + recommended_content_types |
| content_generating → content_ready | content_editor/admin/owner | 已生成至少 1 个 ContentPackage |
| content_ready → verification_pending | content_editor/admin/owner | 有关联 ContentPackage 已标记发布 |
| verification_pending → verified | analyst/admin/owner | 有复测结果或 AttributionResult |
| → dismissed | analyst/admin/owner | 必须填写 dismiss reason |

**ContentPackage 状态流转 + 条件：**

| 流转 | 角色 | 业务条件 |
|------|------|---------|
| draft → fact_checked | 系统/editor | 完成事实检查 |
| fact_checked → needs_review | 系统/editor | medium+ 风险进审核 |
| needs_review → approved | 按风险等级 | 权限通过 |
| approved → exported | content_editor/admin/owner | 已审批 |
| exported → published_marked | content_editor/admin/owner | 必填 publish_url + published_at + platform |
| published_marked → verification_pending | 系统/admin | 已设置复测时间 |
| verification_pending → verified | analyst/admin/owner | 有归因结果 |
| → rejected | legal_reviewer/admin/owner | 必填 rejection reason |

---

### Task 5: API 端点权限 + 审计加固

逐端点改造。覆盖：GT review/promote、Hallucination review、Action transition、Content approve/reject/publish、Report export、Audit log query、User management。

所有端点模式：
```python
@router.post("/xxx")
async def handler(
    resource_id: str,
    body: RequestBody,
    user: User = Depends(require_permission("xxx.xxx")),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    resource = await get_org_xxx_or_404(resource_id, user, db)
    before = snapshot(resource)
    # ... business logic ...
    after = snapshot(resource)
    await add_audit_log(db, user, action, target_type, resource_id,
                        before=before, after=after, request=request)
    await db.commit()
```

---

### Task 6: 审计日志查询 + 脱敏

**文件:** `src/api/audit.py`

```text
GET /api/audit-logs?brand_id=&action=&user_id=&result=&date_from=&date_to=&page=&page_size=
```

- admin/owner 查看组织级（organization_id 隔离）
- 非 admin 返回 403
- detail/before_json/after_json 中的敏感字段（api_key, token, password, secret）自动脱敏
- 支持分页、筛选、按时间排序

---

### Task 7: 前端权限反馈

按钮不可用时保留 disabled + tooltip：
```text
"你当前是 Content Editor，不能审批高风险内容。请联系 Legal Reviewer 或 Admin。"
"该 Action 暂不能发布：缺少 publish_url。"
"你当前是 Viewer，只能查看 Dashboard。"
```

---

### Task 8: 测试（35+ 个）

**文件:** `tests/test_permissions.py`

```text
# 权限 (7)
test_viewer_cannot_review_gt → 403
test_content_editor_cannot_approve_high_risk → 403
test_analyst_cannot_promote_gt → 403
test_admin_can_all_sensitive_actions → 200

# 组织隔离 (5)
test_cross_org_resource_returns_404
test_cannot_access_other_org_action_theme
test_cannot_query_other_org_audit_logs

# 审计 (8)
test_gt_review_writes_audit_log
test_audit_in_same_transaction
test_audit_before_after_snapshots
test_permission_denied_writes_audit

# 状态守卫 (6)
test_publish_requires_url
test_high_risk_requires_legal_reviewer
test_action_requires_content_package_for_ready

# 角色管理 (5)
test_cannot_remove_last_admin
test_admin_cannot_modify_owner
test_role_change_writes_audit

# Request ID (3)
test_request_id_generated_when_missing
test_audit_log_contains_request_id

# 审计脱敏 + append-only (4)
test_audit_payload_masks_api_key
test_no_update_audit_log_endpoint → 404
test_no_delete_audit_log_endpoint → 404
```

---

## 五、验证标准

- [ ] 7 角色体系 + 权限矩阵全部实现
- [ ] 所有敏感 API 有后端权限校验（不依赖前端隐藏）
- [ ] 跨组织访问返回 404
- [ ] 审计日志与业务同事务，含 before/after
- [ ] 审计日志 append-only，敏感字段脱敏
- [ ] RequestIdMiddleware 生成/复用 request_id
- [ ] Action/Content 状态流转有条件守卫
- [ ] 前端按钮 disabled + tooltip 说明原因
- [ ] 113 现有测试继续通过
- [ ] 新增 35+ 测试
