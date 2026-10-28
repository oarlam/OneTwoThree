"""Add ai_suggestion to meetings.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "meetings",
        sa.Column("ai_suggestion", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("meetings", "ai_suggestion")

