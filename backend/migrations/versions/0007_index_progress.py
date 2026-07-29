"""Track asynchronous indexing progress.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "index_profiles",
        sa.Column(
            "processed_chunks",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "index_profiles",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.execute(
        """
        UPDATE index_profiles
        SET processed_chunks = chunk_count
        WHERE status = 'ready'
        """
    )


def downgrade() -> None:
    op.drop_column("index_profiles", "error_message")
    op.drop_column("index_profiles", "processed_chunks")
