"""Initial baseline

Revision ID: 99364ec8454d
Revises:
Create Date: 2026-05-20 11:04:23.521948

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "99364ec8454d"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
