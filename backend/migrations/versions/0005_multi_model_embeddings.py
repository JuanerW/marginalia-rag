"""Store embeddings by model and dimension.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id", "model"),
    )
    op.drop_column("chunks", "embedding")


def downgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(dim=1536),
            nullable=True,
        ),
    )
    op.drop_table("chunk_embeddings")
