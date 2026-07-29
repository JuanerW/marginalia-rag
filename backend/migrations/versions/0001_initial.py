"""Initial reader schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "novels",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("author", sa.String(255)),
        sa.Column("source_filename", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "chapters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("novel_id", sa.Uuid(), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.UniqueConstraint("novel_id", "number"),
    )
    op.create_index("ix_chapters_novel_number", "chapters", ["novel_id", "number"])
    op.create_table(
        "reading_progress",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("novel_id", sa.Uuid(), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reader_key", sa.String(128), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("offset", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("novel_id", "reader_key"),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("novel_id", sa.Uuid(), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536)),
    )
    op.create_index("ix_chunks_read_boundary", "chunks", ["novel_id", "chapter_number", "end_offset"])
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("reading_progress")
    op.drop_table("chapters")
    op.drop_table("novels")
