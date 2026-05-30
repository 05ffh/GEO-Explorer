# P1-3 权限与审核流 实现计划

**日期:** 2026-05-30 | **状态:** Plan | **当前完成度:** 50%

---

## 一、目标

从"定义了 6 个角色 + 前端按钮按角色渲染"升级为"后端强制执行权限 + 所有敏感操作可审计追溯"。

---

## 二、当前状态

| 能力 | 状态 |
|------|------|
| 6 用户角色定义（admin/analyst/gt_reviewer/content_editor/legal_reviewer/viewer） | 已完成 |
| TRANSITION_GUARDS 状态转移权限映射 | 已完成 |
| `can_transition()` 函数 | 已完成 |
| 页面按钮按 `vm.permissions` 条件渲染 | 已完成 |
| 后端 API 强制校验角色 | **缺失** — 当前仅依赖前端隐藏按钮 |
| 审计日志 | **缺失** — 无任何操作记录 |
| RBAC 中间件 / Depends | **缺失** — 每个端点手动判断 |
| 用户管理界面 | **缺失** |

---

## 三、实现任务

### Task 1: 审计日志模型

**文件:** `src/models/audit_log.py`（新建）+ Migration

```python
class AuditLog(Base, UUIDMixin):
    __tablename__ = "audit_logs"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    user_name: Mapped[str] = mapped_column(String(255), default="")
    user_role: Mapped[str] = mapped_column(String(50), default="")
    action: Mapped[str] = mapped_column(String(100), nullable=False)      # gt_review / promote / hallucination_review / action_transition / content_approve / content_publish / report_export
    target_type: Mapped[str] = mapped_column(String(100), default="")     # gt_candidate / action_theme / content_package / brand
    target_id: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)              # {from_status, to_status, field_name, verdict, notes}
    ip_address: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

### Task 2: 审计日志写入工具

**文件:** `src/services/audit.py`（新建）

```python
async def write_audit_log(db, user, action, target_type, target_id, detail=None, request=None):
    log = AuditLog(
        organization_id=user.organization_id, user_id=user.id,
        user_name=user.name or "", user_role=user.role or "",
        action=action, target_type=target_type, target_id=str(target_id),
        detail=detail or {}, ip_address=request.client.host if request else "",
    )
    db.add(log)
    await db.commit()
```

### Task 3: 在现有 API 端点中集成审计 + 权限校验

**涉及文件及操作：**

| 端点 | 权限校验 | 审计日志 action |
|------|---------|----------------|
| `POST /api/gt-candidates/{id}/review` | gt_reviewer / admin | `gt_review` |
| `POST /api/gt-candidates/{id}/promote` | gt_reviewer / admin | `gt_promote` |
| `POST /api/hallucinations/{id}/review` | analyst / gt_reviewer / admin | `hallucination_review` |
| `POST /api/action-themes/{id}/transition` | 按 TRANSITION_GUARDS 校验 | `action_transition` |
| `POST /api/content-packages/{id}/approve` | legal_reviewer / admin | `content_approve` |
| `POST /api/content-packages/{id}/mark-published` | content_editor / admin | `content_publish` |
| `POST /api/dashboard/brands/{id}/reports/generate` | analyst / admin | `report_export` |

### Task 4: RBAC 权限依赖注入

**文件:** `src/api/deps.py`（扩展）

```python
def require_role(*roles: str):
    """FastAPI dependency: raise 403 if user lacks required role."""
    async def checker(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires one of: {roles}")
        return user
    return checker
```

端点使用示例：
```python
@router.post("/gt-candidates/{candidate_id}/promote")
async def promote_candidate(
    candidate_id: str,
    user: User = Depends(require_role("admin", "gt_reviewer")),
    db: AsyncSession = Depends(get_db),
):
    ...
    await write_audit_log(db, user, "gt_promote", "gt_candidate", candidate_id)
```

### Task 5: 审计日志查看页面

**文件:** 在 Dashboard 或设置中添加审计日志列表

```text
GET /api/audit-logs?brand_id=..&action=..&user_id=..&page=..
```

简单表格展示：时间 / 用户 / 角色 / 操作 / 目标 / 详情。

### Task 6: 测试

- 权限拒绝测试（viewer 不能审核 GT、不能 transition Action 等）
- 审计写入测试（操作后日志表有记录）
- 审计查询测试

---

## 四、验证标准

- [ ] Viewer 试图审核 GT → HTTP 403
- [ ] Content Editor 试图 approve 高风险内容 → HTTP 403
- [ ] Admin 审核 GT → 审计日志写入
- [ ] 审计日志可通过 API 查询
- [ ] 现有 113 tests 继续通过
- [ ] 新增 >=10 个权限+审计测试
