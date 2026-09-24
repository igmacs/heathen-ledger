import datetime
import logging
from sqlalchemy.orm import Session
from ..models import Expense, ExpenseSplit, ExpensePayer

logger = logging.getLogger(__name__)


class ExpenseRepository:
    """Repository for Expense, ExpensePayer, and ExpenseSplit persistence."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        group_id: int,
        payer_id: int | None = None,
        amount: int = 0,
        description: str | None = None,
        splits: dict[int, int] | None = None,
        payers: dict[int, int] | None = None,
        expense_date: datetime.date | None = None,
    ) -> Expense:
        """Log a new expense in a group chat."""
        if payers:
            if amount == 0:
                amount = sum(payers.values())
        elif payer_id is not None:
            payers = {payer_id: amount}
        else:
            payers = {}

        expense = Expense(
            group_id=group_id,
            amount=amount,
            description=description,
            expense_date=expense_date,
        )
        self.session.add(expense)
        self.session.flush()

        for p_user_id, p_amount in payers.items():
            payer_entry = ExpensePayer(
                expense_id=expense.id, user_id=p_user_id, amount=p_amount
            )
            self.session.add(payer_entry)

        if splits:
            for user_id, split_amount in splits.items():
                split = ExpenseSplit(
                    expense_id=expense.id, user_id=user_id, amount=split_amount
                )
                self.session.add(split)

        logger.info(
            f"Created expense of {amount} cents in group {group_id} by {len(payers)} payer(s) split among {len(splits or {})} members"
        )
        return expense

    def get_for_group(self, group_id: int) -> list[Expense]:
        """Retrieve all expenses logged in a specific group."""
        return self.session.query(Expense).filter(Expense.group_id == group_id).all()

    def get_by_id(self, expense_id: int) -> Expense | None:
        """Retrieve an expense by ID."""
        return self.session.query(Expense).filter(Expense.id == expense_id).first()

    def delete(self, expense_id: int) -> bool:
        """Delete an expense by ID. Splits are cascade deleted."""
        expense = self.get_by_id(expense_id)
        if expense:
            self.session.delete(expense)
            self.session.flush()
            logger.info(f"Deleted expense ID {expense_id} and its associated splits")
            return True
        return False
