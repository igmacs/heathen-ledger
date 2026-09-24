"""Service layer for balance inspection, debt simplification, and settlement payments."""

from typing import Any
from sqlalchemy.orm import Session

from ..models import User, Group, Payment
from .. import crud
from ..domain.calculations import simplify_debts
from .exceptions import PermissionDeniedError


class SettlementService:
    """Service handling balance calculations, debt simplification, and settlement payments."""

    @classmethod
    def get_group_balances_and_settlements(
        cls, session: Session, group_id: int
    ) -> tuple[dict[int, int], list[dict[str, Any]], dict[int, User]]:
        """Compute current member balances, simplified payback transactions, and user mappings for a group."""
        group = session.query(Group).filter(Group.id == group_id).first()
        if not group or not group.members:
            return {}, [], {}

        balances = crud.get_group_balances(session, group.id)
        transactions = simplify_debts(balances)
        users_by_id = {u.id: u for u in group.members}

        return balances, transactions, users_by_id

    @classmethod
    def record_settlement_payment(
        cls,
        session: Session,
        group: Group,
        clicking_user: User,
        from_id: int,
        to_id: int,
        amount: int,
    ) -> Payment:
        """Validate permissions and log a settlement payment clearing debt between two group members."""
        from_db_user = session.query(User).filter(User.id == from_id).first()
        to_db_user = session.query(User).filter(User.id == to_id).first()

        both_external = (
            from_db_user is not None
            and from_db_user.is_external
            and to_db_user is not None
            and to_db_user.is_external
        )
        if not both_external and clicking_user.id not in (from_id, to_id):
            from_name = from_db_user.first_name if from_db_user else "the debtor"
            to_name = to_db_user.first_name if to_db_user else "the creditor"
            raise PermissionDeniedError(
                f"Only {from_name} or {to_name} can confirm this payment."
            )

        return crud.create_payment(
            session=session,
            group_id=group.id,
            payer_id=from_id,
            payee_id=to_id,
            amount=amount,
        )

    @classmethod
    def is_group_settled(
        cls, session: Session, group_id: int
    ) -> tuple[bool, list[dict[str, Any]], dict[int, User]]:
        """Check whether all debts in a group are fully settled (no remaining payback transactions)."""
        _, transactions, users_by_id = cls.get_group_balances_and_settlements(
            session, group_id
        )
        return len(transactions) == 0, transactions, users_by_id


# Module-level aliases for backwards compatibility
get_group_balances_and_settlements = (
    SettlementService.get_group_balances_and_settlements
)
record_settlement_payment = SettlementService.record_settlement_payment
is_group_settled = SettlementService.is_group_settled
