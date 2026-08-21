"""initial empty anchor

Revision ID: 3b3a06e0a41f
Revises:
Create Date: 2026-08-21 11:08:16.974937

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "3b3a06e0a41f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
