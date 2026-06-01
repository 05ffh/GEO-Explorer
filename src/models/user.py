import uuid
from sqlalchemy import String, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="viewer")
    platform_role: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    # platform_role: system_owner / system_admin / system_operator / None(=org member)
    platform_mfa_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    platform_access_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    organization: Mapped["Organization"] = relationship(back_populates="users")
