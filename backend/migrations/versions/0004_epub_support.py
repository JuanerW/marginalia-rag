"""Add EPUB source and spine metadata."""

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "novels",
        sa.Column("source_format", sa.String(16), nullable=False, server_default="txt"),
    )
    op.add_column("chapters", sa.Column("spine_index", sa.Integer(), nullable=True))
    op.add_column("chapters", sa.Column("source_href", sa.String(1024), nullable=True))
    op.add_column("chapters", sa.Column("fragment_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("chapters", "fragment_id")
    op.drop_column("chapters", "source_href")
    op.drop_column("chapters", "spine_index")
    op.drop_column("novels", "source_format")

