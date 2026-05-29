"""GEO Explorer — Content Management ViewModel."""
from sqlalchemy import select, desc
from src.models.content_package import ContentPackage, CONTENT_PACKAGE_TRANSITIONS


async def build_content_vm(brand, user, db) -> dict:
    """Build view model for the Content management page."""
    return {
        "brand": {"id": str(brand.id), "name": brand.name},
        "packages": [],
    }
