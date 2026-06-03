"""P2-3: Template Review Workbench — add status column to query_templates."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "i1j2k3l4m5n6"
down_revision: Union[str, None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("query_templates",
        sa.Column("status", sa.String(30), server_default="draft", nullable=False))


def downgrade() -> None:
    op.drop_column("query_templates", "status")
