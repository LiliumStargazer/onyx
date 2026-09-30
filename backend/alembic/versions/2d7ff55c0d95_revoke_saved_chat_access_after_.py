"""Revoke saved chat access after Workspace role changes

Revision ID: 2d7ff55c0d95
Revises: a17e7d112017
Create Date: 2026-09-30 18:36:57.012429

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2d7ff55c0d95"
down_revision = "a17e7d112017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_session",
        sa.Column(
            "access_revoked", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_session", "access_revoked")
