"""P2-3: Template CRUD API — create, update, list, validate, preview, status change, clone."""
import uuid
import logging
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_

from src.database import get_db
from src.api.deps import get_current_user
from src.models.user import User
from src.models.query_template import QueryTemplate, QUESTION_TYPES
from src.models.query_template_version import QueryTemplateVersion
from src.services.query_template_versioning import TemplateVersioningService, VersionConflictError
from src.services.template_validation_service import validation_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["templates"])

# ── Permission helpers ──────────────────────────────────────────────────────

def _can_view(user: User) -> bool:
    return user.role in ("admin", "analyst", "gt_reviewer", "viewer", "content_editor",
                         "template_viewer", "template_editor", "template_reviewer",
                         "template_admin") or user.platform_role in ("system_owner", "system_admin")

def _can_edit(user: User) -> bool:
    return user.role in ("admin", "template_editor", "template_reviewer", "template_admin") \
           or user.platform_role in ("system_owner", "system_admin")

def _can_review(user: User) -> bool:
    return user.role in ("admin", "template_reviewer", "template_admin") \
           or user.platform_role in ("system_owner", "system_admin")

def _can_admin(user: User) -> bool:
    return user.role in ("admin", "template_admin") \
           or user.platform_role in ("system_owner", "system_admin")


# ── Pydantic models ─────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    dimension: str = ""
    template_text: str
    priority: int = 0
    question_type: str = "brand_definition"
    brand_directed: float = 1.0
    hallucination_check_enabled: bool = True
    template_level: str = "important"
    question_scope: str | None = None


class TemplateUpdate(BaseModel):
    expected_current_version: int
    change_reason: str = Field(min_length=1)
    changes: dict


class StatusChange(BaseModel):
    expected_current_version: int
    new_status: str  # draft / in_review / active / archived / changes_requested
    reason: str = Field(min_length=1)


class RollbackRequest(BaseModel):
    version: int
    reason: str = Field(min_length=1)
    expected_current_version: int


class ValidateRequest(BaseModel):
    template_text: str
    question_type: str = "brand_definition"
    template_level: str = "important"
    question_scope: str | None = None
    brand_directed: float = 1.0
    applicable_industries: list[str] = []
    excluded_industries: list[str] = []
    metric_eligibility: list[str] = []


class PreviewRequest(BaseModel):
    template_text: str
    brand_name: str = "示例品牌"
    industry: str = "示例行业"
    sample_values: dict = {}


# ── List ────────────────────────────────────────────────────────────────────

@router.get("/api/templates")
async def list_templates(
    question_type: str | None = Query(None),
    template_level: str | None = Query(None),
    status: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_view(user):
        raise HTTPException(403, "无权查看模板列表")
    q = select(QueryTemplate)
    # Multi-tenant: show global + user's org templates
    if user.organization_id:
        q = q.where(
            (QueryTemplate.organization_id == user.organization_id) |
            (QueryTemplate.organization_id.is_(None))
        )
    if question_type:
        q = q.where(QueryTemplate.question_type == question_type)
    if template_level:
        q = q.where(QueryTemplate.template_level == template_level)
    if status:
        q = q.where(QueryTemplate.status == status)
    if is_active is not None:
        q = q.where(QueryTemplate.is_active == is_active)
    q = q.order_by(desc(QueryTemplate.updated_at))
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()
    items = []
    for t in rows:
        items.append({
            "id": str(t.id),
            "dimension": t.dimension,
            "template_text": t.template_text[:100],
            "question_type": t.question_type,
            "template_level": t.template_level,
            "status": t.status,
            "is_active": t.is_active,
            "current_version": t.current_version,
            "priority": t.priority,
            "organization_id": str(t.organization_id) if t.organization_id else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        })
    return {"items": items, "page": page, "page_size": page_size}


# ── Create ──────────────────────────────────────────────────────────────────

@router.post("/api/templates")
async def create_template(
    body: TemplateCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_edit(user):
        raise HTTPException(403, "无权创建模板")
    # Validate
    report = validation_service.validate(
        template_text=body.template_text,
        question_type=body.question_type,
        template_level=body.template_level,
        question_scope=body.question_scope,
        brand_directed=body.brand_directed,
    )
    if not report.valid:
        raise HTTPException(400, detail=report.to_dict())

    svc = TemplateVersioningService()
    template = await svc.create_template(
        db=db,
        organization_id=user.organization_id,
        dimension=body.dimension,
        template_text=body.template_text,
        priority=body.priority,
        question_type=body.question_type,
        brand_directed=body.brand_directed,
        hallucination_check_enabled=body.hallucination_check_enabled,
        template_level=body.template_level,
        question_scope=body.question_scope,
        created_by=user.id,
    )
    # Set status to draft
    template.status = "draft"
    await db.commit()
    return {"id": str(template.id), "current_version": template.current_version, "status": template.status}


# ── Update ──────────────────────────────────────────────────────────────────

@router.put("/api/templates/{template_id}")
async def update_template(
    template_id: str,
    body: TemplateUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_edit(user):
        raise HTTPException(403, "无权编辑模板")
    t = await _get_template_or_404(template_id, user, db)
    if t.status == "active":
        raise HTTPException(400, "active 模板不能直接编辑，请先创建 draft_revision 或联系 reviewer")
    try:
        svc = TemplateVersioningService()
        version = await svc.update_template(
            db=db, template=t,
            changes=body.changes,
            change_reason=body.change_reason,
            expected_current_version=body.expected_current_version,
            user_id=user.id,
        )
        await db.commit()
        return {"id": str(t.id), "current_version": t.current_version, "created_version": version.version if version else t.current_version}
    except VersionConflictError as e:
        raise HTTPException(409, str(e))


# ── Status change ───────────────────────────────────────────────────────────

VALID_STATUS_TRANSITIONS = {
    "draft": {"in_review", "archived"},
    "in_review": {"active", "changes_requested", "draft"},
    "changes_requested": {"draft", "in_review"},
    "active": {"draft_revision", "archived"},
    "draft_revision": {"in_review"},
    "archived": {"draft"},  # clone to draft
}

@router.patch("/api/templates/{template_id}/status")
async def change_template_status(
    template_id: str,
    body: StatusChange,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_template_or_404(template_id, user, db)
    allowed = VALID_STATUS_TRANSITIONS.get(t.status, set())
    if body.new_status not in allowed:
        raise HTTPException(400, f"状态流转非法: {t.status} → {body.new_status}，允许: {allowed}")
    if body.expected_current_version != t.current_version:
        raise HTTPException(409, f"版本冲突: 期望 v{body.expected_current_version}，实际 v{t.current_version}")

    # Publish to active: only reviewer+
    if body.new_status in ("active",):
        if not _can_review(user):
            raise HTTPException(403, "无权发布模板，需要 reviewer 或以上权限")
    # Archive: reviewer+
    if body.new_status in ("archived",):
        if not _can_review(user):
            raise HTTPException(403, "无权归档模板")
    # draft_revision from active: create a new draft version
    if body.new_status == "draft_revision":
        # Clone active template as new draft
        new_t = QueryTemplate(
            organization_id=t.organization_id,
            dimension=t.dimension,
            template_text=t.template_text,
            priority=t.priority,
            question_type=t.question_type,
            brand_directed=t.brand_directed,
            hallucination_check_enabled=t.hallucination_check_enabled,
            template_level=t.template_level,
            question_scope=t.question_scope,
            created_by=user.id,
            status="draft",
            current_version=1,
            is_active=True,
        )
        db.add(new_t)
        await db.flush()
        svc = TemplateVersioningService()
        await svc.create_template(
            db=db, organization_id=t.organization_id,
            dimension=t.dimension, template_text=t.template_text,
            priority=t.priority, question_type=t.question_type,
            brand_directed=t.brand_directed,
            hallucination_check_enabled=t.hallucination_check_enabled,
            template_level=t.template_level,
            question_scope=t.question_scope,
            created_by=user.id,
        )
        # Archive old template
        t.status = "archived"
        t.is_active = False
        await db.commit()
        return {"id": str(new_t.id), "status": "draft", "message": "已从 active 创建 draft_revision"}

    t.status = body.new_status
    if body.new_status == "archived":
        t.is_active = False
    await db.commit()
    return {"id": str(t.id), "status": t.status}


# ── Validate ────────────────────────────────────────────────────────────────

@router.post("/api/templates/validate")
async def validate_template(body: ValidateRequest, user: User = Depends(get_current_user)):
    if not _can_edit(user):
        raise HTTPException(403, "无权校验模板")
    report = validation_service.validate(
        template_text=body.template_text,
        question_type=body.question_type,
        template_level=body.template_level,
        question_scope=body.question_scope,
        brand_directed=body.brand_directed,
        applicable_industries=body.applicable_industries,
        excluded_industries=body.excluded_industries,
        metric_eligibility=body.metric_eligibility,
    )
    return report.to_dict()


# ── Render preview ──────────────────────────────────────────────────────────

@router.post("/api/templates/render-preview")
async def render_preview(body: PreviewRequest, user: User = Depends(get_current_user)):
    if not _can_view(user):
        raise HTTPException(403, "无权预览模板")
    preview = validation_service.render_preview(
        template_text=body.template_text,
        brand_name=body.brand_name,
        industry=body.industry,
        sample_values=body.sample_values,
    )
    return {
        "rendered_question": preview.rendered_question,
        "used_variables": preview.used_variables,
        "missing_variables": preview.missing_variables,
        "fallback_used": preview.fallback_used,
        "warnings": preview.warnings,
        "valid": preview.valid,
    }


# ── Get single template ─────────────────────────────────────────────────────

@router.get("/api/templates/{template_id}")
async def get_template(
    template_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_template_or_404(template_id, user, db)
    return {
        "id": str(t.id),
        "dimension": t.dimension,
        "template_text": t.template_text,
        "priority": t.priority,
        "question_type": t.question_type,
        "brand_directed": t.brand_directed,
        "hallucination_check_enabled": t.hallucination_check_enabled,
        "template_level": t.template_level,
        "question_scope": t.question_scope,
        "status": t.status,
        "is_active": t.is_active,
        "current_version": t.current_version,
        "organization_id": str(t.organization_id) if t.organization_id else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ── Clone ───────────────────────────────────────────────────────────────────

@router.post("/api/templates/{template_id}/clone")
async def clone_template(
    template_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not _can_edit(user):
        raise HTTPException(403, "无权复制模板")
    t = await _get_template_or_404(template_id, user, db)
    new_t = QueryTemplate(
        organization_id=user.organization_id,
        dimension=t.dimension,
        template_text=t.template_text,
        priority=t.priority,
        question_type=t.question_type,
        brand_directed=t.brand_directed,
        hallucination_check_enabled=t.hallucination_check_enabled,
        template_level=t.template_level,
        question_scope=t.question_scope,
        created_by=user.id,
        status="draft",
        current_version=1,
        is_active=True,
    )
    db.add(new_t)
    db.flush()
    svc = TemplateVersioningService()
    await svc.create_template(
        db=db,
        organization_id=user.organization_id,
        dimension=t.dimension,
        template_text=t.template_text,
        priority=t.priority,
        question_type=t.question_type,
        brand_directed=t.brand_directed,
        hallucination_check_enabled=t.hallucination_check_enabled,
        template_level=t.template_level,
        question_scope=t.question_scope,
        created_by=user.id,
    )
    await db.commit()
    return {"id": str(new_t.id), "status": "draft", "source_template_id": template_id}


# ── KPI recommendation matrix ──────────────────────────────────────────────

@router.get("/api/templates/kpi-matrix")
async def get_kpi_matrix(user: User = Depends(get_current_user)):
    from src.services.template_validation_service import _QTYPE_KPI_MATRIX
    return _QTYPE_KPI_MATRIX


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _get_template_or_404(template_id: str, user: User, db: AsyncSession) -> QueryTemplate:
    t = (await db.execute(select(QueryTemplate).where(QueryTemplate.id == template_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "模板不存在")
    # Multi-tenant: org users can only access own + global templates
    if t.organization_id and user.organization_id and t.organization_id != user.organization_id:
        raise HTTPException(404, "模板不存在")
    return t
