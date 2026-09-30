"""Service layer for expense recording, participant toggling, payback logging, and transaction undo."""

from typing import Any

from sqlalchemy.orm import Session

from ..domain.calculations import split_amount_equally
from ..dto import ParsedPaybackCommand, ParsedPayCommand
from ..formatters import format_cents
from ..models import Expense, ExpenseSplit, Group, Payment, User
from ..repositories import ExpenseRepository, PaymentRepository, UserRepository
from .exceptions import PermissionDeniedError, UserNotFoundError, ValidationError


class ExpenseService:
    """Service handling expense creation, split participant toggles, paybacks, and undos."""

    @classmethod
    def record_expense(
        cls,
        session: Session,
        group: Group,
        sender: User,
        command: ParsedPayCommand,
    ) -> Expense:
        """Validate payers and split specifications, calculate shares, and create a persistent Expense."""
        payers_dict = cls._resolve_payers(session, group, sender, command.payers)
        splits_dict = cls._resolve_splits(
            session, group, sender, command.split_spec, command.amount
        )

        # 3. Create the expense in database
        return ExpenseRepository(session).create(
            group_id=group.id,
            amount=command.amount,
            description=command.description,
            splits=splits_dict,
            payers=payers_dict,
            expense_date=command.expense_date,
        )

    @classmethod
    def _resolve_user(
        cls, session: Session, group: Group, sender: User, uname: str
    ) -> User:
        user_repo = UserRepository(session)
        if uname == "me":
            u = sender
        else:
            u = user_repo.get_in_group(group_id=group.id, username=uname)
            if not u:
                raise UserNotFoundError(uname)
        user_repo.add_to_group(user=u, group=group)
        return u

    @classmethod
    def _resolve_payers(
        cls, session: Session, group: Group, sender: User, payers: dict[str, int]
    ) -> dict[int, int]:
        payers_dict = {}
        for uname, p_cents in payers.items():
            u = cls._resolve_user(session, group, sender, uname)
            payers_dict[u.id] = p_cents
        return payers_dict

    @classmethod
    def _resolve_equal_splits(
        cls, participants: list[User], amount: int
    ) -> dict[int, int]:
        shares = split_amount_equally(amount, len(participants))
        return {u.id: s for u, s in zip(participants, shares)}

    @classmethod
    def _resolve_splits(
        cls,
        session: Session,
        group: Group,
        sender: User,
        split_spec: Any,
        amount: int,
    ) -> dict[int, int]:
        mode = split_spec.mode
        if mode == "all":
            if not group.members:
                raise ValidationError(
                    "No participants found to split the expense with."
                )
            return cls._resolve_equal_splits(group.members, amount)

        elif mode == "except":
            excluded = set(split_spec.excluded)
            participants = [
                m for m in group.members if (m.username or "").lower() not in excluded
            ]
            if not participants:
                raise ValidationError(
                    "No participants left to split the expense with after exclusions."
                )
            return cls._resolve_equal_splits(participants, amount)

        elif mode == "subset":
            participants = [
                cls._resolve_user(session, group, sender, uname)
                for uname in split_spec.participants
            ]
            if not participants:
                raise ValidationError(
                    "No participants found to split the expense with."
                )
            return cls._resolve_equal_splits(participants, amount)

        elif mode == "custom":
            splits_dict = {}
            for uname, share_cents in split_spec.shares.items():
                u = cls._resolve_user(session, group, sender, uname)
                splits_dict[u.id] = share_cents
            return splits_dict

        return {}

    @classmethod
    def toggle_split_participant(
        cls,
        session: Session,
        expense_id: int,
        target_user_id: int,
        clicking_user: User,
        creator_id: int,
    ) -> Expense:
        """Toggle a participant in an expense split and recalculate equal shares."""
        if clicking_user.id != creator_id:
            creator_user = session.query(User).filter(User.id == creator_id).first()
            creator_name = (
                creator_user.first_name if creator_user else "the user who recorded it"
            )
            raise PermissionDeniedError(f"Only {creator_name} can edit this split.")

        expense = session.query(Expense).filter(Expense.id == expense_id).first()
        if not expense:
            raise ValidationError("Expense not found or already deleted.")

        current_splits = {s.user_id: s for s in expense.splits}
        if target_user_id in current_splits:
            if len(current_splits) <= 1:
                raise ValidationError(
                    "Cannot remove the last participant from the split."
                )
            session.delete(current_splits[target_user_id])
            current_splits.pop(target_user_id)
        else:
            new_split = ExpenseSplit(
                expense_id=expense.id, user_id=target_user_id, amount=0
            )
            session.add(new_split)
            current_splits[target_user_id] = new_split

        session.flush()

        num_people = len(current_splits)
        shares = split_amount_equally(expense.amount, num_people)
        sorted_remaining_ids = sorted(current_splits.keys())
        for user_id, share in zip(sorted_remaining_ids, shares):
            current_splits[user_id].amount = share

        session.commit()
        session.refresh(expense)
        return expense

    @classmethod
    def record_payback(
        cls,
        session: Session,
        group: Group,
        sender: User,
        command: ParsedPaybackCommand,
    ) -> Payment:
        """Validate payer and payee and record a direct settlement payment."""
        user_repo = UserRepository(session)
        if command.payer_username:
            payer = user_repo.get_in_group(group.id, command.payer_username)
            if not payer:
                raise UserNotFoundError(command.payer_username)
        else:
            payer = sender

        payee = user_repo.get_in_group(group.id, command.payee_username)
        if not payee:
            raise UserNotFoundError(command.payee_username)

        user_repo.add_to_group(payer, group)
        user_repo.add_to_group(payee, group)

        return PaymentRepository(session).create(
            group_id=group.id,
            payer_id=payer.id,
            payee_id=payee.id,
            amount=command.amount,
        )

    @classmethod
    def undo_transaction(
        cls,
        session: Session,
        tx_type: str,
        tx_id: int,
        clicking_user: User,
        creator_id: int,
    ) -> str:
        """Authorize and delete a transaction, returning an audit description of the undone item."""
        if clicking_user.id != creator_id:
            creator_user = session.query(User).filter(User.id == creator_id).first()
            creator_name = (
                creator_user.first_name if creator_user else "the user who recorded it"
            )
            raise PermissionDeniedError(
                f"Only {creator_name} can undo this transaction."
            )

        success = False
        audit_desc = ""
        if tx_type == "expense":
            expense = session.query(Expense).filter(Expense.id == tx_id).first()
            if expense:
                amount_formatted = format_cents(expense.amount)
                desc_str = (
                    f" for '{expense.description}'" if expense.description else ""
                )
                audit_desc = f"Recorded expense of {amount_formatted}{desc_str}"
                success = ExpenseRepository(session).delete(tx_id)
        elif tx_type == "payment":
            payment = session.query(Payment).filter(Payment.id == tx_id).first()
            if payment:
                amount_formatted = format_cents(payment.amount)
                audit_desc = f"Recorded payment of {amount_formatted}"
                success = PaymentRepository(session).delete(tx_id)

        if not success:
            raise ValidationError("Transaction not found or already deleted.")

        return audit_desc


# Module-level aliases for backwards compatibility
record_expense = ExpenseService.record_expense
toggle_split_participant = ExpenseService.toggle_split_participant
record_payback = ExpenseService.record_payback
undo_transaction = ExpenseService.undo_transaction
