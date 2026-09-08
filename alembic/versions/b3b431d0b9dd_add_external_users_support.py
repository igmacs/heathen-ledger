"""add_external_users_support

Revision ID: b3b431d0b9dd
Revises: cc782c837f27
Create Date: 2026-09-08 15:09:08.183500

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3b431d0b9dd"
down_revision: Union[str, Sequence[str], None] = "cc782c837f27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_external", sa.Boolean(), server_default=sa.false(), nullable=False
            )
        )
        batch_op.alter_column(
            "telegram_id", existing_type=sa.BigInteger(), nullable=True
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column(
            "telegram_id", existing_type=sa.BigInteger(), nullable=False
        )
        batch_op.drop_column("is_external")
