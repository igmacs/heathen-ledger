"""CRUD and database persistence facade delegating to specialized repository classes."""

import datetime
from typing import Any

from sqlalchemy.orm import Session

from .domain import BalanceCalculator
from .models import Expense, Group, Payment, User
from .repositories import (
    ExpenseRepository,
    GroupRepository,
    PaymentRepository,
    UserRepository,
)

# --- User Helpers ---


def get_user_by_telegram_id(session: Session, telegram_id: int) -> User | None:
    """Retrieve a user by their unique Telegram user ID."""
    return UserRepository(session).get_by_telegram_id(telegram_id)


def get_or_create_user(
    session: Session,
    telegram_id: int,
    username: str | None = None,
    first_name: str = "",
) -> User:
    """Get an existing user or create a new user registry if they do not exist."""
    return UserRepository(session).get_or_create(
        telegram_id=telegram_id, username=username, first_name=first_name
    )


def create_external_user(
    session: Session,
    group: Group,
    first_name: str,
    username: str | None = None,
) -> User:
    """Register an external user (without a Telegram account) and add them to the group."""
    return UserRepository(session).create_external(
        group=group, first_name=first_name, username=username
    )


def get_user_in_group(
    session: Session,
    group_id: int,
    username: str,
) -> User | None:
    """Find a user in a specific group by username or first name."""
    return UserRepository(session).get_in_group(group_id=group_id, username=username)


def add_user_to_group(session: Session, user: User, group: Group) -> bool:
    """Add a user to a group chat's member list if not already present."""
    return UserRepository(session).add_to_group(user=user, group=group)


# --- Group Helpers ---


def get_group_by_telegram_id(session: Session, telegram_chat_id: int) -> Group | None:
    """Retrieve a group by its Telegram chat ID."""
    return GroupRepository(session).get_by_telegram_id(telegram_chat_id)


def get_or_create_group(
    session: Session, telegram_chat_id: int, title: str | None = None
) -> Group:
    """Get an existing group chat or register a new one if it does not exist."""
    return GroupRepository(session).get_or_create(
        telegram_chat_id=telegram_chat_id, title=title
    )


def delete_group(session: Session, group: Group) -> None:
    """Delete a group and its associated external members from the database."""
    GroupRepository(session).delete(group)


# --- Expense & Split Helpers ---


def create_expense(
    session: Session,
    group_id: int,
    payer_id: int | None = None,
    amount: int = 0,
    description: str | None = None,
    splits: dict[int, int] | None = None,
    payers: dict[int, int] | None = None,
    expense_date: datetime.date | None = None,
) -> Expense:
    """Log a new expense in a group chat."""
    return ExpenseRepository(session).create(
        group_id=group_id,
        payer_id=payer_id,
        amount=amount,
        description=description,
        splits=splits,
        payers=payers,
        expense_date=expense_date,
    )


def get_group_expenses(session: Session, group_id: int) -> list[Expense]:
    """Retrieve all expenses logged in a specific group."""
    return ExpenseRepository(session).get_for_group(group_id)


def delete_expense(session: Session, expense_id: int) -> bool:
    """Delete an expense by its ID."""
    return ExpenseRepository(session).delete(expense_id)


# --- Payment / Settlement Helpers ---


def create_payment(
    session: Session, group_id: int, payer_id: int, payee_id: int, amount: int
) -> Payment:
    """Log a direct payback payment where one member pays back another."""
    return PaymentRepository(session).create(
        group_id=group_id, payer_id=payer_id, payee_id=payee_id, amount=amount
    )


def get_group_payments(session: Session, group_id: int) -> list[Payment]:
    """Retrieve all logged payments in a specific group."""
    return PaymentRepository(session).get_for_group(group_id)


def delete_payment(session: Session, payment_id: int) -> bool:
    """Delete a payback payment by its ID."""
    return PaymentRepository(session).delete(payment_id)


# --- Balance Calculation & Transaction History ---


def get_group_balances(session: Session, group_id: int) -> dict[int, int]:
    """Calculate the net balance for each member in a group chat."""
    group = GroupRepository(session).get_by_id(group_id)
    if not group:
        return {}

    expenses = ExpenseRepository(session).get_for_group(group_id)
    payments = PaymentRepository(session).get_for_group(group_id)
    return BalanceCalculator.calculate_net_balances(
        members=group.members, expenses=expenses, payments=payments
    )


def get_recent_transactions(
    session: Session, group_id: int, limit: int = 10
) -> list[dict[str, Any]]:
    """Retrieve recent transactions (both expenses and payments) in a group."""
    return PaymentRepository(session).get_recent_transactions(
        group_id=group_id, limit=limit
    )
