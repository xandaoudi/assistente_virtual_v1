"""create user_channels table

Revision ID: 99aad9e57e3b
Revises: 2bec0fb9e2c0
Create Date: 2026-08-23 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "99aad9e57e3b"
down_revision: str | Sequence[str] | None = "2bec0fb9e2c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column(
            "linked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("channel", "external_id", name="uq_user_channels_channel_external_id"),
    )
    op.create_index("ix_user_channels_user_id", "user_channels", ["user_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_user_channels_user_id", table_name="user_channels")
    op.drop_table("user_channels")
