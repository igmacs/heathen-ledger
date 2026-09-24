"""Service layer for querying and managing transaction history and deletions."""

from typing import Any

from sqlalchemy.orm import Session

from ..models import User
from ..repositories import ExpenseRepository, PaymentRepository
from .exceptions import PermissionDeniedError, ValidationError


class HistoryService:
    """Service handling transaction history querying and deletion authorization."""

    @classmethod
    def get_recent_transactions(
        cls, session: Session, group_id: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Retrieve recent transactions (both expenses and payments) sorted descending by created_at."""
        payment_repo = PaymentRepository(session)
        return payment_repo.get_recent_transactions(group_id=group_id, limit=limit)

    @classmethod
    def delete_transaction(
        cls,
        session: Session,
        tx_type: str,
        tx_id: int,
        clicking_user: User,
    ) -> str:
        """Authorize and delete a transaction, returning a confirmation message."""
        if tx_type == "expense":
            expense_repo = ExpenseRepository(session)
            expense = expense_repo.get_by_id(tx_id)
            if not expense:
                raise ValidationError("Expense not found or already deleted.")

            payer_ids = {p.user_id for p in expense.payers} if expense.payers else set()

            if clicking_user.id not in payer_ids:
                if (
                    expense.payers
                    and len(expense.payers) == 1
                    and expense.payers[0].user
                ):
                    payer_name = expense.payers[0].user.first_name
                elif expense.payers:
                    payer_name = "one of the payers"
                else:
                    payer_name = "the payer"
                raise PermissionDeniedError(
                    f"Only {payer_name} can delete this expense."
                )

            expense_repo.delete(tx_id)
            session.commit()
            return "Expense deleted."

        elif tx_type == "payment":
            payment_repo = PaymentRepository(session)
            payment = payment_repo.get_by_id(tx_id)
            if not payment:
                raise ValidationError("Payment not found or already deleted.")

            if clicking_user.id not in (payment.payer_id, payment.payee_id):
                payer_name = payment.payer.first_name if payment.payer else "the payer"
                payee_name = payment.payee.first_name if payment.payee else "the payee"
                raise PermissionDeniedError(
                    f"Only {payer_name} or {payee_name} can delete this payment."
                )

            payment_repo.delete(tx_id)
            session.commit()
            return "Payment deleted."

        else:
            raise ValidationError(f"Invalid transaction type: '{tx_type}'")


# Module-level aliases for backwards compatibility
get_recent_transactions = HistoryService.get_recent_transactions
delete_transaction = HistoryService.delete_transaction
