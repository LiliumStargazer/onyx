"""Add Workspace content role to users.

Revision ID: a17e7d112017
Revises: 47cf9a997ddc
"""

from alembic import op
import sqlalchemy as sa

revision: str = "a17e7d112017"
down_revision: str | None = "47cf9a997ddc"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    op.add_column("user", sa.Column("workspace_role", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "workspace_role")
