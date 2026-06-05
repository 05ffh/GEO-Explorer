"""P2-FRONTEND: Action workbench VM — kanban with real themes, plans, packages."""
from sqlalchemy import select, func
from src.models.action_theme import ActionTheme
from src.models.action_plan import ActionPlan
from src.models.content_package import ContentPackage

TRANSITION_GUARDS = {
    ("detected", "confirmed"): ("admin", "analyst", "gt_reviewer"),
    ("confirmed", "content_generating"): ("admin", "content_editor"),
    ("confirmed", "dismissed"): ("admin", "analyst", "gt_reviewer"),
    ("content_generating", "content_ready"): ("admin", "content_editor"),
    ("content_ready", "approved"): ("admin", "legal_reviewer"),
    ("content_ready", "dismissed"): ("admin", "content_editor"),
    ("approved", "published_marked"): ("admin", "content_editor"),
    ("published_marked", "verification_pending"): ("admin",),
    ("verification_pending", "verified"): ("admin", "analyst"),
}

PLAN_TRANSITIONS = {
    "pending": ["in_progress", "cancelled"],
    "in_progress": ["completed", "cancelled"],
    "completed": ["verified", "reopened"],
    "verified": [], "cancelled": [], "reopened": ["in_progress"],
}


def can_transition(user_role: str, from_status: str, to_status: str) -> bool:
    return user_role in TRANSITION_GUARDS.get((from_status, to_status), ())


async def build_action_vm(brand, filters, user, db) -> dict:
    # Themes
    themes_q = select(ActionTheme).where(
        ActionTheme.brand_id == brand.id,
        ActionTheme.status.in_(("detected","confirmed","content_generating","content_ready","approved")),
    ).order_by(ActionTheme.priority.desc()).limit(50)
    themes = (await db.execute(themes_q)).scalars().all()

    # Plans
    plans_q = select(ActionPlan).where(
        ActionPlan.brand_id == brand.id,
    ).order_by(ActionPlan.priority.desc(), ActionPlan.created_at.desc()).limit(50)
    plans = (await db.execute(plans_q)).scalars().all()

    # Content packages
    pkg_q = select(ContentPackage).where(ContentPackage.brand_id == brand.id).order_by(ContentPackage.created_at.desc()).limit(30)
    packages = (await db.execute(pkg_q)).scalars().all()

    t_rows = []
    for t in themes:
        av = [to for (frm,to),roles in TRANSITION_GUARDS.items() if frm == t.status and user.role in roles]
        t_rows.append({
            "id": str(t.id), "title": t.title or f"{t.issue_type or 'action'}",
            "priority": t.priority, "status": t.status,
            "issue_type": t.issue_type or "", "affected_fields": t.affected_fields or [],
            "typical_claims": (t.typical_ai_claims or [])[:3],
            "effort_level": t.effort_level or "medium",
            "expected_kpi_impact": t.expected_kpi_impact or {},
            "hallucination_count": len(t.hallucination_result_ids or []),
            "plan_count": len(t.action_plan_ids or []),
            "transitions": av,
        })

    p_rows = []
    for p in plans:
        av = PLAN_TRANSITIONS.get(p.status, [])
        p_rows.append({
            "id": str(p.id), "trigger_type": p.trigger_type or "",
            "action_type": p.action_type or "", "priority": p.priority,
            "status": p.status, "notes": p.notes or "",
            "suggested_content_type": p.suggested_content_type or "",
            "transitions": av,
        })

    pkg_rows = []
    for cp in packages:
        pkg_rows.append({
            "id": str(cp.id), "status": cp.status,
            "risk_level": cp.risk_level or "low",
            "content_count": len(cp.content_items or []),
            "published_platform": cp.published_platform or "",
            "publish_summary": cp.publish_status_summary or "",
        })

    # Generation preconditions
    from src.models.collection_run import CollectionRun
    latest_run = (await db.execute(
        select(CollectionRun).where(
            CollectionRun.brand_id == brand.id,
            CollectionRun.collection_status.in_(["completed", "partial"]),
        ).order_by(CollectionRun.collection_completed_at.desc()).limit(1)
    )).scalar_one_or_none()

    can_generate = user.role in ("admin", "analyst", "owner") \
                   or user.platform_role in ("system_owner", "system_admin")
    gen_disabled_reason = ""
    if not can_generate:
        gen_disabled_reason = "需要管理员权限"
    elif not latest_run:
        gen_disabled_reason = "没有已完成的诊断 Run，请先启动诊断"

    # Per-action content generation flags
    for plan in p_rows:
        plan["can_generate_content"] = plan.get("status") not in ("closed", "archived", "rejected") \
                                       and user.role in ("admin", "content_editor") \
                                       or user.platform_role in ("system_owner", "system_admin")
        plan["generate_content_disabled_reason"] = ""
        if plan.get("status") in ("closed", "archived", "rejected"):
            plan["generate_content_disabled_reason"] = "该 Action 已关闭/归档"
        elif not plan["can_generate_content"]:
            plan["generate_content_disabled_reason"] = "需要 Content Editor 权限"

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "themes": t_rows,
        "plans": p_rows,
        "packages": pkg_rows,
        "columns": ["detected","confirmed","content_generating","content_ready","approved"],
        "permissions": {
            "can_manage": user.role in ("admin","analyst","gt_reviewer","content_editor","legal_reviewer"),
            "role": user.role,
            "can_generate_actions": can_generate and latest_run is not None,
            "generate_disabled_reason": gen_disabled_reason,
        },
        "generation": {
            "can_generate": can_generate and latest_run is not None,
            "disabled_reason": gen_disabled_reason,
            "latest_run_id": str(latest_run.id) if latest_run else None,
            "latest_run_status": latest_run.collection_status if latest_run else None,
            "existing_actions": len(p_rows),
        },
        "total_themes": len(t_rows),
        "total_plans": len(p_rows),
    }
