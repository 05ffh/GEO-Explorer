"""P2-1: Claim Taxonomy — add claim_type + predicate_type to hallucination_results.

Revision ID: g1h2i3j4k5l6
Create Date: 2026-06-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hallucination_results",
        sa.Column("claim_type", sa.String(20), server_default="unknown", nullable=False))
    op.add_column("hallucination_results",
        sa.Column("predicate_type", sa.String(30), server_default="other", nullable=False))
    op.create_index("ix_hallucination_results_claim_type", "hallucination_results", ["claim_type"])


def downgrade() -> None:
    op.drop_index("ix_hallucination_results_claim_type")
    op.drop_column("hallucination_results", "predicate_type")
    op.drop_column("hallucination_results", "claim_type")
