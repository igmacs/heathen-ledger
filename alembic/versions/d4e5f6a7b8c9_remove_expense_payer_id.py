"""remove_expense_payer_id

Revision ID: d4e5f6a7b8c9
Revises: b3b431d0b9dd
Create Date: 2026-09-21 18:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "b3b431d0b9dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: backfill expense_payers and drop expenses.payer_id."""
    # 1. Backfill any expense that has a payer_id but no entry in expense_payers
    op.execute(
        """
        INSERT INTO expense_payers (expense_id, user_id, amount)
        SELECT id, payer_id, amount FROM expenses
        WHERE payer_id IS NOT NULL
          AND id NOT IN (SELECT DISTINCT expense_id FROM expense_payers)
        """
    )
    # 2. Drop the payer_id column from expenses
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.drop_index("ix_expenses_payer_id")
        batch_op.drop_column("payer_id")


def downgrade() -> None:
    """Downgrade schema: restore expenses.payer_id and populate it."""
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("payer_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_expenses_payer_id_users",
            "users",
            ["payer_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_expenses_payer_id", ["payer_id"], unique=False)

    # Populate payer_id from expense_payers where there is a single payer
    op.execute(
        """
        UPDATE expenses
        SET payer_id = (
            SELECT user_id FROM expense_payers
            WHERE expense_payers.expense_id = expenses.id
            GROUP BY expense_id
            HAVING COUNT(*) = 1
        )
        """
    )
