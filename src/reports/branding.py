"""Report branding — three-layer inheritance + validation (P2-3)."""
import re
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.report_delivery import ReportBranding

logger = logging.getLogger(__name__)

HEX_PATTERN = re.compile(r'^#[0-9a-fA-F]{6}$')
FONT_ALLOWLIST = {"Fira Sans", "Fira Code", "Inter", "Noto Sans CJK SC", "Source Han Sans SC"}
DEFAULT_BRANDING = {
    "primary_color": "#1E40AF",
    "accent_color": "#3B82F6",
    "font_heading": "Fira Sans",
    "font_body": "Fira Sans",
    "logo_url": None,
    "footer_text": None,
    "company_name_display": None,
    "hide_geo_branding": False,
}


async def resolve_branding(brand_id, org_id, db: AsyncSession) -> dict:
    """Resolve brand > organization > platform_default branding."""
    # 1. Brand-level
    if brand_id:
        result = await db.execute(
            select(ReportBranding).where(
                ReportBranding.brand_id == brand_id,
                ReportBranding.scope == "brand",
                ReportBranding.is_active == True,
            ).limit(1)
        )
        b = result.scalar_one_or_none()
        if b:
            return _to_dict(b, "brand")

    # 2. Organization-level
    if org_id:
        result = await db.execute(
            select(ReportBranding).where(
                ReportBranding.organization_id == org_id,
                ReportBranding.scope == "organization",
                ReportBranding.is_active == True,
            ).limit(1)
        )
        o = result.scalar_one_or_none()
        if o:
            return _to_dict(o, "organization")

    # 3. Platform default
    result = await db.execute(
        select(ReportBranding).where(
            ReportBranding.scope == "platform",
            ReportBranding.is_active == True,
        ).limit(1)
    )
    p = result.scalar_one_or_none()
    if p:
        return _to_dict(p, "platform")

    return {"scope": "default", "resolved_from": "builtin", **DEFAULT_BRANDING}


def _to_dict(b, scope: str) -> dict:
    return {
        "scope": scope,
        "resolved_from": scope,
        "primary_color": b.primary_color,
        "accent_color": b.accent_color,
        "font_heading": b.font_heading,
        "font_body": b.font_body,
        "logo_url": b.logo_url,
        "footer_text": b.footer_text,
        "company_name_display": b.company_name_display,
        "hide_geo_branding": b.hide_geo_branding,
    }


def validate_branding(data: dict) -> list[str]:
    """Validate branding fields. Returns list of error messages."""
    errors = []

    if "primary_color" in data and not HEX_PATTERN.match(data["primary_color"]):
        errors.append("primary_color 必须是合法 HEX 颜色，如 #1E40AF")
    if "accent_color" in data and not HEX_PATTERN.match(data["accent_color"]):
        errors.append("accent_color 必须是合法 HEX 颜色，如 #3B82F6")

    if "logo_url" in data and data["logo_url"]:
        url = data["logo_url"]
        if not url.startswith("https://"):
            errors.append("logo_url 必须使用 HTTPS")
        if len(url) > 500:
            errors.append("logo_url 超过 500 字符")

    for font_key in ("font_heading", "font_body"):
        if font_key in data and data[font_key] not in FONT_ALLOWLIST:
            errors.append(f"{font_key} 不在可用字体列表中: {sorted(FONT_ALLOWLIST)}")

    if "footer_text" in data and data["footer_text"]:
        # Strip HTML tags
        from html import escape
        data["footer_text"] = escape(data["footer_text"])[:500]

    return errors
