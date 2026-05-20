"""Initial baseline

Revision ID: 99364ec8454d
Revises:
Create Date: 2026-05-20 11:04:23.521948

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "99364ec8454d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
