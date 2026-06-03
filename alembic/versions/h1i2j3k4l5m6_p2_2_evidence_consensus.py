"""P2-2: Multi-Evidence GT — add evidence_consensus_json to hallucination_results.

Revision ID: h1i2j3k4l5m6
Create Date: 2026-06-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hallucination_results",
        sa.Column("evidence_consensus_json", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("hallucination_results", "evidence_consensus_json")
