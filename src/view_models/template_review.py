"""P2-3: Template review workbench view models."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.models.query_template import QueryTemplate, QUESTION_TYPES
from src.models.query_template_version import QueryTemplateVersion
from src.models.user import User


async def build_template_list_vm(user: User, db: AsyncSession, filters: dict | None = None) -> dict:
    """Build view model for template list page."""
    f = filters or {}
    q = select(QueryTemplate)
    if user.organization_id:
        q = q.where(
            (QueryTemplate.organization_id == user.organization_id) |
            (QueryTemplate.organization_id.is_(None))
        )
    if f.get("question_type"):
        q = q.where(QueryTemplate.question_type == f["question_type"])
    if f.get("template_level"):
        q = q.where(QueryTemplate.template_level == f["template_level"])
    if f.get("status"):
        q = q.where(QueryTemplate.status == f["status"])
    q = q.order_by(QueryTemplate.updated_at.desc()).limit(50)
    rows = (await db.execute(q)).scalars().all()

    templates = []
    for t in rows:
        templates.append({
            "id": str(t.id),
            "dimension": t.dimension,
            "template_text_preview": t.template_text[:120],
            "question_type": t.question_type,
            "template_level": t.template_level,
            "status": t.status,
            "is_active": t.is_active,
            "current_version": t.current_version,
            "priority": t.priority,
            "is_global": t.organization_id is None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else "",
        })

    # Permission flags
    is_editor = user.role in ("admin", "template_editor", "template_reviewer", "template_admin") \
                or user.platform_role in ("system_owner", "system_admin")
    is_reviewer = user.role in ("admin", "template_reviewer", "template_admin") \
                  or user.platform_role in ("system_owner", "system_admin")

    return {
        "templates": templates,
        "question_types": QUESTION_TYPES,
        "template_levels": ["critical", "important", "optional"],
        "statuses": ["draft", "in_review", "active", "changes_requested", "archived"],
        "total_count": len(templates),
        "permissions": {
            "can_edit": is_editor,
            "can_review": is_reviewer,
        },
    }


async def build_template_editor_vm(template_id: str, user: User, db: AsyncSession) -> dict:
    """Build view model for template editor page."""
    t = (await db.execute(select(QueryTemplate).where(QueryTemplate.id == template_id))).scalar_one_or_none()
    if not t:
        return {"error": "模板不存在"}

    # Permission check
    is_editor = user.role in ("admin", "template_editor", "template_reviewer", "template_admin") \
                or user.platform_role in ("system_owner", "system_admin")
    is_reviewer = user.role in ("admin", "template_reviewer", "template_admin") \
                  or user.platform_role in ("system_owner", "system_admin")

    if t.organization_id and user.organization_id and t.organization_id != user.organization_id:
        return {"error": "无权访问此模板"}

    # Version history
    versions = (await db.execute(
        select(QueryTemplateVersion).where(
            QueryTemplateVersion.template_id == template_id
        ).order_by(QueryTemplateVersion.version.desc()).limit(20)
    )).scalars().all()

    version_list = []
    for v in versions:
        version_list.append({
            "version": v.version,
            "change_type": v.change_type if hasattr(v, "change_type") else "",
            "change_reason": v.change_reason if hasattr(v, "change_reason") else "",
            "created_at": v.created_at.isoformat() if v.created_at else "",
        })

    from src.schemas.industry_profiles import IndustryCode
    industries = [{"code": c.value, "label": c.value} for c in IndustryCode]

    # KPI matrix for the frontend
    from src.services.template_validation_service import _QTYPE_KPI_MATRIX
    kpi_matrix = _QTYPE_KPI_MATRIX.get(t.question_type, {})

    return {
        "template": {
            "id": str(t.id),
            "dimension": t.dimension,
            "template_text": t.template_text,
            "priority": t.priority,
            "question_type": t.question_type,
            "brand_directed": t.brand_directed,
            "hallucination_check_enabled": t.hallucination_check_enabled,
            "template_level": t.template_level,
            "question_scope": t.question_scope or "",
            "status": t.status,
            "is_active": t.is_active,
            "current_version": t.current_version,
            "is_global": t.organization_id is None,
        },
        "versions": version_list,
        "industries": industries,
        "question_types": QUESTION_TYPES,
        "template_levels": ["critical", "important", "optional"],
        "question_scopes": ["", "brand_directed", "brand_adjacent", "category_directed", "scenario_directed", "generic"],
        "brand_directed_options": [0, 0.25, 0.5, 0.75, 1.0],
        "kpi_matrix": kpi_matrix,
        "status_transitions": {
            "draft": ["in_review", "archived"],
            "in_review": ["active", "changes_requested", "draft"],
            "changes_requested": ["draft", "in_review"],
            "active": ["draft_revision", "archived"],
            "archived": ["draft"],
        },
        "permissions": {
            "can_edit": is_editor,
            "can_review": is_reviewer,
        },
    }
