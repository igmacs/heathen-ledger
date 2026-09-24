import logging
from typing import Any
from sqlalchemy.orm import Session
from ..models import Payment, Expense

logger = logging.getLogger(__name__)


class PaymentRepository:
    """Repository for Payment (settlement payback) records and transaction history queries."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, group_id: int, payer_id: int, payee_id: int, amount: int
    ) -> Payment:
        """Log a direct payback payment where one member pays back another."""
        payment = Payment(
            group_id=group_id, payer_id=payer_id, payee_id=payee_id, amount=amount
        )
        self.session.add(payment)
        self.session.flush()
        logger.info(
            f"Logged payment of {amount} cents from user ID {payer_id} to user ID {payee_id}"
        )
        return payment

    def get_for_group(self, group_id: int) -> list[Payment]:
        """Retrieve all logged payments in a specific group."""
        return self.session.query(Payment).filter(Payment.group_id == group_id).all()

    def get_by_id(self, payment_id: int) -> Payment | None:
        """Retrieve a payment by ID."""
        return self.session.query(Payment).filter(Payment.id == payment_id).first()

    def delete(self, payment_id: int) -> bool:
        """Delete a payback payment by ID."""
        payment = self.get_by_id(payment_id)
        if payment:
            self.session.delete(payment)
            self.session.flush()
            logger.info(f"Deleted payment ID {payment_id}")
            return True
        return False

    def get_recent_transactions(
        self, group_id: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Retrieve recent transactions (expenses and payments) sorted descending by created_at."""
        expenses = (
            self.session.query(Expense)
            .filter(Expense.group_id == group_id)
            .order_by(Expense.created_at.desc())
            .limit(limit)
            .all()
        )
        payments = (
            self.session.query(Payment)
            .filter(Payment.group_id == group_id)
            .order_by(Payment.created_at.desc())
            .limit(limit)
            .all()
        )

        txs = []
        for exp in expenses:
            txs.append({"type": "expense", "obj": exp, "created_at": exp.created_at})
        for pay in payments:
            txs.append({"type": "payment", "obj": pay, "created_at": pay.created_at})

        txs.sort(key=lambda x: x["created_at"], reverse=True)
        return txs[:limit]
