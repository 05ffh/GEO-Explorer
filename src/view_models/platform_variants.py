"""View model for Platform Variants workbench (P0-9)."""

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.content_package import ContentPackage
from src.models.brand import Brand
from src.models.user import User
from src.actions.platform_policy import PLATFORM_KNOWLEDGE_SOURCE_POLICY


async def build_platform_variants_vm(
    cp_id: str, brand: Brand, user: User, db: AsyncSession,
) -> dict:
    cp = (await db.execute(
        select(ContentPackage).where(ContentPackage.id == cp_id)
    )).scalar_one_or_none()
    if not cp:
        return {"error": "ContentPackage not found"}

    pv = cp.platform_variants or {}
    content_items = cp.content_items or []

    # Build variant list per platform
    platforms = []
    total_variants = 0
    total_approved = 0

    for plat_key in ["deepseek_kimi", "doubao", "wenxin"]:
        vlist = pv.get(plat_key, [])
        if not vlist:
            continue

        policy = PLATFORM_KNOWLEDGE_SOURCE_POLICY.get(
            "deepseek" if plat_key == "deepseek_kimi" else plat_key, {}
        )
        items = []
        for vi, v in enumerate(vlist):
            status = v.get("status", "draft")
            compliance = v.get("compliance_flags", [])
            total_variants += 1
            if status == "approved":
                total_approved += 1

            items.append({
                "index": vi,
                "format": v.get("format", ""),
                "target": v.get("target", ""),
                "theme": v.get("theme", ""),
                "title": v.get("title") or v.get("seo_title") or v.get("entry_name", ""),
                "body": (v.get("body_markdown") or v.get("markdown") or "")[:500],
                "full_body": v.get("body_markdown") or v.get("markdown") or "",
                "status": status,
                "word_count": v.get("word_count", 0),
                "version": v.get("version", 1),
                "input_fact_ids": v.get("input_fact_ids", []),
                "evidence_ids": v.get("evidence_ids", []),
                "claim_check_status": v.get("claim_check_status", "pending"),
                "compliance_flags": compliance,
                "compliance_passed": not any(f["severity"] == "high" for f in compliance),
                "published_url": v.get("published_url") or "",
                "published_at": v.get("published_at") or "",
                "tags": v.get("tags", []),
                "jsonld": v.get("jsonld") or [],
                "schema_types": v.get("schema_types") or [],
            })

        platforms.append({
            "key": plat_key,
            "label": PLATFORM_LABELS.get(plat_key, plat_key),
            "sources": policy.get("assumed_sources", []),
            "auto_publish": policy.get("auto_publish_possible", False),
            "variants": items,
        })

    # Content items from the CP
    themes = []
    for ci in content_items:
        themes.append({
            "type": ci.get("type", ""),
            "theme": ci.get("theme", ""),
            "title": ci.get("title", ""),
            "source_fields": ci.get("source_fields", []),
        })

    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "cp": {
            "id": str(cp.id),
            "status": cp.status,
            "risk_level": cp.risk_level,
            "gt_snapshot_hash": cp.gt_snapshot_hash or "",
            "has_variants": total_variants > 0,
        },
        "platforms": platforms,
        "themes": themes,
        "total_variants": total_variants,
        "total_approved": total_approved,
        "permissions": {
            "can_generate": True,
            "can_approve": True,
            "can_export": True,
        },
    }


PLATFORM_LABELS = {
    "deepseek_kimi": "DeepSeek / Kimi",
    "doubao": "Doubao",
    "wenxin": "Wenxin",
}
