"""P1-7: Template versioning API — list, detail, diff, rollback."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from src.database import get_db
from src.api.deps import get_current_user
from src.models.user import User
from src.models.query_template import QueryTemplate
from src.models.query_template_version import QueryTemplateVersion
from src.services.query_template_versioning import TemplateVersioningService, VersionConflictError

router = APIRouter(prefix="/api/templates", tags=["template-versions"])


class RollbackRequest(BaseModel):
    version: int
    reason: str = Field(..., min_length=1)
    expected_current_version: int


@router.get("/{template_id}/versions")
async def list_versions(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tmpl = await _get_template(db, template_id)
    _check_org_access(tmpl, user)
    versions = (await db.execute(
        select(QueryTemplateVersion)
        .where(QueryTemplateVersion.template_id == template_id)
        .order_by(desc(QueryTemplateVersion.version))
    )).scalars().all()
    return {
        "template_id": str(template_id),
        "current_version": tmpl.current_version,
        "versions": [
            {
                "version": v.version,
                "change_type": v.change_type,
                "change_reason": v.change_reason,
                "rollback_from_version": v.rollback_from_version,
                "created_by": str(v.created_by) if v.created_by else None,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
    }


@router.get("/{template_id}/versions/{version}")
async def get_version_detail(
    template_id: uuid.UUID,
    version: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tmpl = await _get_template(db, template_id)
    _check_org_access(tmpl, user)
    ver = (await db.execute(
        select(QueryTemplateVersion).where(
            QueryTemplateVersion.template_id == template_id,
            QueryTemplateVersion.version == version,
        )
    )).scalar_one_or_none()
    if ver is None:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    return _version_to_dict(ver)


@router.get("/{template_id}/versions/{from_version}/diff/{to_version}")
async def diff_versions(
    template_id: uuid.UUID,
    from_version: int,
    to_version: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tmpl = await _get_template(db, template_id)
    _check_org_access(tmpl, user)
    v_from = (await db.execute(
        select(QueryTemplateVersion).where(
            QueryTemplateVersion.template_id == template_id,
            QueryTemplateVersion.version == from_version,
        )
    )).scalar_one_or_none()
    v_to = (await db.execute(
        select(QueryTemplateVersion).where(
            QueryTemplateVersion.template_id == template_id,
            QueryTemplateVersion.version == to_version,
        )
    )).scalar_one_or_none()
    if v_from is None or v_to is None:
        raise HTTPException(status_code=404, detail="Version not found")

    diffs = []
    for field in QueryTemplate.VERSIONED_FIELDS:
        old_val = getattr(v_from, field)
        new_val = getattr(v_to, field)
        if old_val != new_val:
            diffs.append({"field": field, "from": old_val, "to": new_val})
    return {
        "template_id": str(template_id),
        "from_version": from_version,
        "to_version": to_version,
        "diffs": diffs,
    }


@router.post("/{template_id}/rollback")
async def rollback_template(
    template_id: uuid.UUID,
    body: RollbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tmpl = await _get_template(db, template_id)
    _check_org_access(tmpl, user)
    try:
        ver = await TemplateVersioningService.rollback_template(
            db,
            template_id=template_id,
            target_version=body.version,
            reason=body.reason,
            user_id=user.id,
            expected_current_version=body.expected_current_version,
        )
    except VersionConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _version_to_dict(ver)


async def _get_template(db: AsyncSession, template_id: uuid.UUID) -> QueryTemplate:
    tmpl = (await db.execute(
        select(QueryTemplate).where(QueryTemplate.id == template_id)
    )).scalar_one_or_none()
    if tmpl is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return tmpl


def _check_org_access(tmpl: QueryTemplate, user: User):
    """P0-6: Tenant isolation — org-specific templates only visible to org members."""
    if tmpl.organization_id is None:
        return  # Global template, visible to all
    if user.organization_id != tmpl.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")


def _version_to_dict(ver: QueryTemplateVersion) -> dict:
    return {
        "id": str(ver.id),
        "template_id": str(ver.template_id),
        "version": ver.version,
        "organization_id": str(ver.organization_id) if ver.organization_id else None,
        "dimension": ver.dimension,
        "template_text": ver.template_text,
        "priority": ver.priority,
        "question_type": ver.question_type,
        "brand_directed": ver.brand_directed,
        "hallucination_check_enabled": ver.hallucination_check_enabled,
        "template_level": ver.template_level,
        "question_scope": ver.question_scope,
        "change_type": ver.change_type,
        "change_reason": ver.change_reason,
        "rollback_from_version": ver.rollback_from_version,
        "created_by": str(ver.created_by) if ver.created_by else None,
        "created_at": ver.created_at.isoformat() if ver.created_at else None,
    }
