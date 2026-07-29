"""Add novel import metadata."""

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("novels", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("novels", sa.Column("encoding", sa.String(32), nullable=True))
    op.execute("UPDATE novels SET content_hash = md5(id::text), encoding = 'unknown'")
    op.alter_column("novels", "content_hash", nullable=False)
    op.alter_column("novels", "encoding", nullable=False)
    op.create_unique_constraint("uq_novels_content_hash", "novels", ["content_hash"])


def downgrade() -> None:
    op.drop_constraint("uq_novels_content_hash", "novels", type_="unique")
    op.drop_column("novels", "encoding")
    op.drop_column("novels", "content_hash")
