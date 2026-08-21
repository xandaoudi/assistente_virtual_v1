"""create categories table

Revision ID: 58446d98444b
Revises: 47d894b40607
Create Date: 2026-08-21 15:45:51.528172

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "58446d98444b"
down_revision: str | Sequence[str] | None = "47d894b40607"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column(
            "type",
            sa.Enum("expense", "income", name="transaction_type", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=20), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("user_id", "name", "type", name="uq_categories_user_id_name_type"),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_categories_user_id", table_name="categories")
    op.drop_table("categories")
