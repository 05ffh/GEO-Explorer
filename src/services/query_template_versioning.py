"""TemplateVersioningService — explicit template versioning with FOR UPDATE concurrency control.

P1-7: All template mutations (create/update/rollback) go through this service.
The service is the single source of truth for versioned field changes.
"""
import uuid
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.query_template import QueryTemplate
from src.models.query_template_version import QueryTemplateVersion

logger = logging.getLogger(__name__)

CHANGE_CREATE = "create"
CHANGE_UPDATE = "update"
CHANGE_ROLLBACK = "rollback"


class VersionConflictError(Exception):
    """Raised when expected_current_version doesn't match the DB."""
    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(f"Version conflict: expected {expected}, current {actual}")


class TemplateVersioningService:
    @staticmethod
    async def create_template(
        db: AsyncSession,
        *,
        organization_id: uuid.UUID | None = None,
        dimension: str,
        template_text: str,
        priority: int = 0,
        question_type: str = "brand_definition",
        brand_directed: float = 1.0,
        hallucination_check_enabled: bool = True,
        template_level: str = "important",
        question_scope: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> tuple[QueryTemplate, QueryTemplateVersion]:
        """Create template + v1 within a single transaction (P0-2)."""
        tmpl = QueryTemplate(
            organization_id=organization_id,
            dimension=dimension,
            template_text=template_text,
            priority=priority,
            question_type=question_type,
            brand_directed=brand_directed,
            hallucination_check_enabled=hallucination_check_enabled,
            template_level=template_level,
            question_scope=question_scope,
            is_active=True,
            current_version=1,
            created_by=created_by,
        )
        db.add(tmpl)
        await db.flush()

        ver = _build_version_snapshot(tmpl, 1, CHANGE_CREATE, created_by, change_reason=None)
        db.add(ver)
        await db.flush()

        return tmpl, ver

    @staticmethod
    async def update_template(
        db: AsyncSession,
        *,
        template_id: uuid.UUID,
        changes: dict,
        changed_by: uuid.UUID,
        change_reason: str | None = None,
        expected_current_version: int | None = None,
    ) -> QueryTemplate | None:
        """Update template fields + create version snapshot (P0-3).

        Uses FOR UPDATE to serialize concurrent modifications.
        Returns None if no versioned fields actually changed.
        Raises VersionConflictError if expected_current_version mismatches.
        """
        # Lock and load
        tmpl = (await db.execute(
            select(QueryTemplate).where(QueryTemplate.id == template_id).with_for_update()
        )).scalar_one_or_none()

        if tmpl is None:
            raise ValueError(f"Template {template_id} not found")

        if expected_current_version is not None and tmpl.current_version != expected_current_version:
            raise VersionConflictError(expected_current_version, tmpl.current_version)

        # Detect which versioned fields actually change
        changed_versioned_fields = {}
        for field in QueryTemplate.VERSIONED_FIELDS:
            if field in changes:
                old_val = getattr(tmpl, field)
                new_val = changes[field]
                if old_val != new_val:
                    changed_versioned_fields[field] = new_val

        if not changed_versioned_fields:
            non_versioned = {k: v for k, v in changes.items() if k not in QueryTemplate.VERSIONED_FIELDS}
            for k, v in non_versioned.items():
                setattr(tmpl, k, v)
            await db.flush()
            return None

        for k, v in changes.items():
            setattr(tmpl, k, v)
        new_version = tmpl.current_version + 1
        ver = _build_version_snapshot(tmpl, new_version, CHANGE_UPDATE, changed_by, change_reason)
        tmpl.current_version = new_version

        db.add(ver)
        await db.flush()
        return ver

    @staticmethod
    async def rollback_template(
        db: AsyncSession,
        *,
        template_id: uuid.UUID,
        target_version: int,
        reason: str,
        user_id: uuid.UUID,
        expected_current_version: int,
    ) -> QueryTemplateVersion:
        """Rollback to a specific version, creating a new rollback version (P0-4).

        Steps:
        1. FOR UPDATE lock template
        2. Verify expected_current_version
        3. Load target version snapshot
        4. Restore versioned fields to template
        5. Insert new version with change_type=rollback
        """
        tmpl = (await db.execute(
            select(QueryTemplate).where(QueryTemplate.id == template_id).with_for_update()
        )).scalar_one_or_none()

        if tmpl is None:
            raise ValueError(f"Template {template_id} not found")

        if tmpl.current_version != expected_current_version:
            raise VersionConflictError(expected_current_version, tmpl.current_version)

        # Load target version
        target = (await db.execute(
            select(QueryTemplateVersion).where(
                QueryTemplateVersion.template_id == template_id,
                QueryTemplateVersion.version == target_version,
            )
        )).scalar_one_or_none()

        if target is None:
            raise ValueError(f"Version {target_version} not found for template {template_id}")

        # Restore versioned fields from target snapshot
        for field in QueryTemplate.VERSIONED_FIELDS:
            setattr(tmpl, field, getattr(target, field))
        new_version = tmpl.current_version + 1
        ver = _build_version_snapshot(
            tmpl, new_version, CHANGE_ROLLBACK, user_id,
            change_reason=reason, rollback_from_version=target_version,
        )
        tmpl.current_version = new_version

        db.add(ver)
        await db.flush()
        return ver


def _build_version_snapshot(
    tmpl: QueryTemplate,
    version: int,
    change_type: str,
    created_by: uuid.UUID | None,
    change_reason: str | None = None,
    rollback_from_version: int | None = None,
) -> QueryTemplateVersion:
    """Build a QueryTemplateVersion snapshot from the current template state."""
    return QueryTemplateVersion(
        template_id=tmpl.id,
        version=version,
        organization_id=tmpl.organization_id,
        dimension=tmpl.dimension,
        template_text=tmpl.template_text,
        priority=tmpl.priority,
        question_type=tmpl.question_type,
        brand_directed=tmpl.brand_directed,
        hallucination_check_enabled=tmpl.hallucination_check_enabled,
        template_level=tmpl.template_level,
        question_scope=tmpl.question_scope,
        change_type=change_type,
        change_reason=change_reason,
        rollback_from_version=rollback_from_version,
        created_by=created_by,
    )
