"""Service layer for expense recording, participant toggling, payback logging, and transaction undo."""

from sqlalchemy.orm import Session

from ..models import User, Group, Expense, Payment, ExpenseSplit
from .. import crud
from ..domain.calculations import split_amount_equally
from ..formatters import format_cents
from ..dto import ParsedPayCommand, ParsedPaybackCommand
from .exceptions import UserNotFoundError, ValidationError, PermissionDeniedError


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
        # 1. Resolve Payers
        payers_dict = {}
        for uname, p_cents in command.payers.items():
            if uname == "me":
                u = sender
            else:
                u = crud.get_user_in_group(session, group.id, uname)
                if not u:
                    raise UserNotFoundError(uname)
            crud.add_user_to_group(session, u, group)
            payers_dict[u.id] = p_cents

        # 2. Resolve Participants and Splits
        split_mode = command.split_spec.mode
        splits_dict = {}

        if split_mode == "all":
            participants = group.members
            if not participants:
                raise ValidationError(
                    "No participants found to split the expense with."
                )
            shares = split_amount_equally(command.amount, len(participants))
            for u, s in zip(participants, shares, strict=False):
                splits_dict[u.id] = s

        elif split_mode == "except":
            excluded = set(command.split_spec.excluded)
            participants = [
                m for m in group.members if (m.username or "").lower() not in excluded
            ]
            if not participants:
                raise ValidationError(
                    "No participants left to split the expense with after exclusions."
                )
            shares = split_amount_equally(command.amount, len(participants))
            for u, s in zip(participants, shares, strict=False):
                splits_dict[u.id] = s

        elif split_mode == "subset":
            participants = []
            for uname in command.split_spec.participants:
                if uname == "me":
                    u = sender
                else:
                    u = crud.get_user_in_group(session, group.id, uname)
                    if not u:
                        raise UserNotFoundError(uname)
                crud.add_user_to_group(session, u, group)
                participants.append(u)

            if not participants:
                raise ValidationError(
                    "No participants found to split the expense with."
                )
            shares = split_amount_equally(command.amount, len(participants))
            for u, s in zip(participants, shares, strict=False):
                splits_dict[u.id] = s

        elif split_mode == "custom":
            for uname, share_cents in command.split_spec.shares.items():
                if uname == "me":
                    u = sender
                else:
                    u = crud.get_user_in_group(session, group.id, uname)
                    if not u:
                        raise UserNotFoundError(uname)
                crud.add_user_to_group(session, u, group)
                splits_dict[u.id] = share_cents

        # 3. Create the expense in database
        return crud.create_expense(
            session=session,
            group_id=group.id,
            amount=command.amount,
            description=command.description,
            splits=splits_dict,
            payers=payers_dict,
            expense_date=command.expense_date,
        )

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
        for user_id, share in zip(sorted_remaining_ids, shares, strict=False):
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
        if command.payer_username:
            payer = crud.get_user_in_group(session, group.id, command.payer_username)
            if not payer:
                raise UserNotFoundError(command.payer_username)
        else:
            payer = sender

        payee = crud.get_user_in_group(session, group.id, command.payee_username)
        if not payee:
            raise UserNotFoundError(command.payee_username)

        crud.add_user_to_group(session, payer, group)
        crud.add_user_to_group(session, payee, group)

        return crud.create_payment(
            session=session,
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
                success = crud.delete_expense(session, tx_id)
        elif tx_type == "payment":
            payment = session.query(Payment).filter(Payment.id == tx_id).first()
            if payment:
                amount_formatted = format_cents(payment.amount)
                audit_desc = f"Recorded payment of {amount_formatted}"
                success = crud.delete_payment(session, tx_id)

        if not success:
            raise ValidationError("Transaction not found or already deleted.")

        return audit_desc


# Module-level aliases for backwards compatibility
record_expense = ExpenseService.record_expense
toggle_split_participant = ExpenseService.toggle_split_participant
record_payback = ExpenseService.record_payback
undo_transaction = ExpenseService.undo_transaction
