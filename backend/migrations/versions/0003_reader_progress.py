"""Track display and furthest read positions."""

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column("reading_progress", "chapter_number", new_column_name="display_chapter_number")
    op.alter_column("reading_progress", "offset", new_column_name="display_offset")
    op.add_column(
        "reading_progress",
        sa.Column("furthest_chapter_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "reading_progress",
        sa.Column("furthest_offset", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE reading_progress SET "
        "furthest_chapter_number = display_chapter_number, "
        "furthest_offset = display_offset"
    )
    op.alter_column("reading_progress", "furthest_chapter_number", nullable=False)
    op.alter_column("reading_progress", "furthest_offset", nullable=False)


def downgrade() -> None:
    op.drop_column("reading_progress", "furthest_offset")
    op.drop_column("reading_progress", "furthest_chapter_number")
    op.alter_column("reading_progress", "display_offset", new_column_name="offset")
    op.alter_column(
        "reading_progress",
        "display_chapter_number",
        new_column_name="chapter_number",
    )

