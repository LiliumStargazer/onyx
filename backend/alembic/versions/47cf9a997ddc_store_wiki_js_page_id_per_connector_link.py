"""Store Wiki.js page ID per connector link.

Revision ID: 47cf9a997ddc
Revises: ac05f4a21dbd
"""

from alembic import op
import sqlalchemy as sa

revision = "47cf9a997ddc"
down_revision = "ac05f4a21dbd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_by_connector_credential_pair",
        sa.Column("wikijs_page_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_by_connector_credential_pair", "wikijs_page_id")
