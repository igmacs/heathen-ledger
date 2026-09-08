"""add_expense_payers_and_expense_date

Revision ID: cc782c837f27
Revises: 6ede661b74cd
Create Date: 2026-09-08 14:02:14.785158

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cc782c837f27"
down_revision: Union[str, Sequence[str], None] = "6ede661b74cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "expense_payers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("expense_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expense_payers_expense_id"),
        "expense_payers",
        ["expense_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expense_payers_user_id"), "expense_payers", ["user_id"], unique=False
    )
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("expense_date", sa.Date(), nullable=True))
        batch_op.alter_column("payer_id", existing_type=sa.INTEGER(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("expenses", schema=None) as batch_op:
        batch_op.alter_column("payer_id", existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column("expense_date")
    op.drop_index(op.f("ix_expense_payers_user_id"), table_name="expense_payers")
    op.drop_index(op.f("ix_expense_payers_expense_id"), table_name="expense_payers")
    op.drop_table("expense_payers")
