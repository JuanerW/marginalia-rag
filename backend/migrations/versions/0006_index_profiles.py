"""Preserve multiple chunking and embedding profiles.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "index_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("novel_id", sa.Uuid(), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("target_size", sa.Integer(), nullable=False),
        sa.Column("max_size", sa.Integer(), nullable=False),
        sa.Column("overlap", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=True),
        sa.Column("chapter_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["novel_id"],
            ["novels.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "chunks",
        sa.Column("index_profile_id", sa.Uuid(), nullable=True),
    )
    op.execute(
        """
        INSERT INTO index_profiles (
            id, novel_id, strategy, target_size, max_size, overlap,
            embedding_model, dimensions, chapter_count, chunk_count,
            status, is_active
        )
        SELECT
            gen_random_uuid(), c.novel_id, 'paragraph', 700, 900, 100,
            COALESCE(MIN(ce.model), 'bge-m3:latest'),
            MIN(ce.dimensions),
            COUNT(DISTINCT c.chapter_id),
            COUNT(DISTINCT c.id),
            'ready',
            TRUE
        FROM chunks c
        LEFT JOIN chunk_embeddings ce ON ce.chunk_id = c.id
        GROUP BY c.novel_id
        """
    )
    op.execute(
        """
        UPDATE chunks c
        SET index_profile_id = p.id
        FROM index_profiles p
        WHERE p.novel_id = c.novel_id
          AND c.index_profile_id IS NULL
        """
    )
    op.alter_column("chunks", "index_profile_id", nullable=False)
    op.create_foreign_key(
        "chunks_index_profile_id_fkey",
        "chunks",
        "index_profiles",
        ["index_profile_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chunks_index_profile_id_fkey",
        "chunks",
        type_="foreignkey",
    )
    op.drop_column("chunks", "index_profile_id")
    op.drop_table("index_profiles")
