"""create transactions table

Revision ID: e224fa330efd
Revises: 58446d98444b
Create Date: 2026-08-21 15:54:37.032244

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e224fa330efd"
down_revision: str | Sequence[str] | None = "58446d98444b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "type",
            sa.Enum("expense", "income", name="transaction_type", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=40), nullable=True),
        sa.Column(
            "source",
            sa.Enum(
                "chat",
                "receipt",
                "import",
                "recurring",
                name="transaction_source",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_transactions_user_id_date", "transactions", ["user_id", "date"])
    op.create_index(
        "ix_transactions_user_id_category_id_date",
        "transactions",
        ["user_id", "category_id", "date"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_transactions_user_id_category_id_date", table_name="transactions")
    op.drop_index("ix_transactions_user_id_date", table_name="transactions")
    op.drop_table("transactions")
