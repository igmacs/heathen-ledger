import datetime
import logging
from typing import Optional, Dict, List, Any
from sqlalchemy.orm import Session
from .models import User, Group, Expense, ExpenseSplit, Payment, ExpensePayer

logger = logging.getLogger(__name__)


# --- User Helper Functions ---


def get_user_by_telegram_id(session: Session, telegram_id: int) -> Optional[User]:
    """Retrieve a user by their unique Telegram user ID."""
    return session.query(User).filter(User.telegram_id == telegram_id).first()


def get_or_create_user(
    session: Session,
    telegram_id: int,
    username: Optional[str] = None,
    first_name: str = "",
) -> User:
    """Get an existing user or create a new user registry if they do not exist."""
    user = get_user_by_telegram_id(session, telegram_id)
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            is_external=False,
        )
        session.add(user)
        session.flush()
        logger.info(f"Registered new user: {first_name} (Telegram ID: {telegram_id})")
    else:
        # Keep username and first name updated
        if username is not None and user.username != username:
            user.username = username
        if first_name and user.first_name != first_name:
            user.first_name = first_name
    return user


def create_external_user(
    session: Session,
    group: Group,
    first_name: str,
    username: Optional[str] = None,
) -> User:
    """
    Register an external user (without a Telegram account) and add them to the group.
    """
    clean_username = username.lower().lstrip("@") if username else None
    user = User(
        telegram_id=None,
        username=clean_username,
        first_name=first_name,
        is_external=True,
    )
    session.add(user)
    session.flush()
    add_user_to_group(session, user, group)
    logger.info(
        f"Registered external user: {first_name} (@{clean_username}) in group {group.title}"
    )
    return user


def get_user_in_group(
    session: Session,
    group_id: int,
    username: str,
) -> Optional[User]:
    """
    Find a user in a specific group by username or first name.
    If not found in group members, falls back to globally registered Telegram users.
    """
    clean_name = username.strip().lower().lstrip("@")
    group = session.query(Group).filter(Group.id == group_id).first()
    if group:
        # 1. Match username in group members
        for m in group.members:
            if m.username and m.username.lower() == clean_name:
                return m
        # 2. Match first name in group members
        for m in group.members:
            if m.first_name and m.first_name.lower() == clean_name:
                return m

    # 3. Fallback: Search globally for registered non-external Telegram users
    fallback_user = (
        session.query(User)
        .filter(User.username == clean_name, User.is_external.is_(False))
        .first()
    )
    if fallback_user and group:
        add_user_to_group(session, fallback_user, group)
    return fallback_user


# --- Group Helper Functions ---


def get_group_by_telegram_id(
    session: Session, telegram_chat_id: int
) -> Optional[Group]:
    """Retrieve a group by its Telegram chat ID."""
    return (
        session.query(Group).filter(Group.telegram_chat_id == telegram_chat_id).first()
    )


def get_or_create_group(
    session: Session, telegram_chat_id: int, title: Optional[str] = None
) -> Group:
    """Get an existing group chat or register a new one if it does not exist."""
    group = get_group_by_telegram_id(session, telegram_chat_id)
    if not group:
        group = Group(telegram_chat_id=telegram_chat_id, title=title)
        session.add(group)
        session.flush()
        logger.info(f"Registered new group chat: {title} (Chat ID: {telegram_chat_id})")
    else:
        if title is not None and group.title != title:
            group.title = title
    return group


def add_user_to_group(session: Session, user: User, group: Group) -> bool:
    """Add a user to a group chat's member list if not already present."""
    if user not in group.members:
        group.members.append(user)
        logger.info(f"Added user {user.first_name} to group {group.title}")
        return True
    return False


# --- Expense & Split Helper Functions ---


def create_expense(
    session: Session,
    group_id: int,
    payer_id: Optional[int] = None,
    amount: int = 0,
    description: Optional[str] = None,
    splits: Optional[Dict[int, int]] = None,
    payers: Optional[Dict[int, int]] = None,
    expense_date: Optional[datetime.date] = None,
) -> Expense:
    """
    Log a new expense in a group chat.

    :param session: The database session.
    :param group_id: Internal primary key of the group.
    :param payer_id: Internal primary key of the user who paid (optional if payers given).
    :param amount: Total expense amount in cents (inferred from payers if 0).
    :param description: What the expense was for.
    :param splits: A dictionary mapping internal user IDs (user_id: int)
                  to their individual owed amount in cents (split_amount: int).
    :param payers: A dictionary mapping internal user IDs (user_id: int)
                   to the amount in cents they paid (amount: int).
    :param expense_date: The date on which the expense occurred (optional, defaults to None).
    """
    if payers:
        if amount == 0:
            amount = sum(payers.values())
        if payer_id is None:
            payer_id = next(iter(payers)) if len(payers) == 1 else None
    elif payer_id is not None:
        payers = {payer_id: amount}
    else:
        payers = {}

    expense = Expense(
        group_id=group_id,
        payer_id=payer_id,
        amount=amount,
        description=description,
        expense_date=expense_date,
    )
    session.add(expense)
    session.flush()

    for p_user_id, p_amount in payers.items():
        payer_entry = ExpensePayer(
            expense_id=expense.id, user_id=p_user_id, amount=p_amount
        )
        session.add(payer_entry)

    if splits:
        for user_id, split_amount in splits.items():
            split = ExpenseSplit(
                expense_id=expense.id, user_id=user_id, amount=split_amount
            )
            session.add(split)

    logger.info(
        f"Created expense of {amount} cents in group {group_id} by {len(payers)} payer(s) split among {len(splits or {})} members"
    )
    return expense


def get_group_expenses(session: Session, group_id: int) -> List[Expense]:
    """Retrieve all expenses logged in a specific group."""
    return session.query(Expense).filter(Expense.group_id == group_id).all()


# --- Payment / Settlement Helper Functions ---


def create_payment(
    session: Session, group_id: int, payer_id: int, payee_id: int, amount: int
) -> Payment:
    """Log a direct payment where one member pays back another member to settle debt."""
    payment = Payment(
        group_id=group_id, payer_id=payer_id, payee_id=payee_id, amount=amount
    )
    session.add(payment)
    session.flush()
    logger.info(
        f"Logged payment of {amount} cents from user ID {payer_id} to user ID {payee_id}"
    )
    return payment


def get_group_payments(session: Session, group_id: int) -> List[Payment]:
    """Retrieve all logged payments/settlements in a specific group."""
    return session.query(Payment).filter(Payment.group_id == group_id).all()


# --- Balance Calculation Layer ---


def get_group_balances(session: Session, group_id: int) -> Dict[int, int]:
    """
    Calculate the net balance for each member in a group chat.

    Net Balance = (Paid in Expenses) - (Owed in Splits) + (Received in Payments) - (Sent in Payments)

    - Positive balance: The user is owed money (they paid more than they owed).
    - Negative balance: The user owes money (they owed more than they paid).
    - Zero balance: The user is fully settled up.

    :return: A dict mapping internal user IDs to their net balance in cents.
    """
    balances = {}

    group = session.query(Group).filter(Group.id == group_id).first()
    if not group:
        return balances

    # Initialize all members with a 0 balance
    for member in group.members:
        balances[member.id] = 0

    # 1. Process Expenses and Splits
    expenses = get_group_expenses(session, group_id)
    for exp in expenses:
        if exp.payers:
            for p in exp.payers:
                if p.user_id not in balances:
                    balances[p.user_id] = 0
                balances[p.user_id] += p.amount
        elif exp.payer_id:
            if exp.payer_id not in balances:
                balances[exp.payer_id] = 0
            balances[exp.payer_id] += exp.amount

        for split in exp.splits:
            if split.user_id not in balances:
                balances[split.user_id] = 0
            balances[split.user_id] -= split.amount

    # 2. Process Settlement Payments
    payments = get_group_payments(session, group_id)
    for pay in payments:
        if pay.payer_id not in balances:
            balances[pay.payer_id] = 0
        if pay.payee_id not in balances:
            balances[pay.payee_id] = 0

        # Payer sent money -> their debt decreases / they are closer to settled (add amount)
        balances[pay.payer_id] += pay.amount
        # Payee received money -> what they are owed decreases / they are closer to settled (subtract amount)
        balances[pay.payee_id] -= pay.amount

    return balances


def get_recent_transactions(
    session: Session, group_id: int, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Retrieve recent transactions (both expenses and payments) in a group,
    merged and sorted by creation date descending.
    """
    expenses = (
        session.query(Expense)
        .filter(Expense.group_id == group_id)
        .order_by(Expense.created_at.desc())
        .limit(limit)
        .all()
    )
    payments = (
        session.query(Payment)
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

    # Sort descending
    txs.sort(key=lambda x: x["created_at"], reverse=True)
    return txs[:limit]


def delete_expense(session: Session, expense_id: int) -> bool:
    """Delete an expense by its ID. Splits will be cascade-deleted by the database."""
    expense = session.query(Expense).filter(Expense.id == expense_id).first()
    if expense:
        session.delete(expense)
        session.flush()
        logger.info(f"Deleted expense ID {expense_id} and its associated splits")
        return True
    return False


def delete_payment(session: Session, payment_id: int) -> bool:
    """Delete a payback payment by its ID."""
    payment = session.query(Payment).filter(Payment.id == payment_id).first()
    if payment:
        session.delete(payment)
        session.flush()
        logger.info(f"Deleted payment ID {payment_id}")
        return True
    return False
