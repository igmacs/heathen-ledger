from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# Many-to-many relationship mapping between users and groups
group_members = Table(
    "group_members",
    Base.metadata,
    Column(
        "group_id",
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True, index=True
    )
    username: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    is_external: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    groups: Mapped[list[Group]] = relationship(
        "Group", secondary=group_members, back_populates="members"
    )
    expense_contributions: Mapped[list[ExpensePayer]] = relationship(
        "ExpensePayer", back_populates="user"
    )
    splits: Mapped[list[ExpenseSplit]] = relationship(
        "ExpenseSplit", back_populates="user"
    )
    payments_sent: Mapped[list[Payment]] = relationship(
        "Payment", foreign_keys="Payment.payer_id", back_populates="payer"
    )
    payments_received: Mapped[list[Payment]] = relationship(
        "Payment", foreign_keys="Payment.payee_id", back_populates="payee"
    )


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC),
        nullable=True,
    )

    # Relationships
    members: Mapped[list[User]] = relationship(
        "User", secondary=group_members, back_populates="groups"
    )
    expenses: Mapped[list[Expense]] = relationship(
        "Expense", back_populates="group", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(
        "Payment", back_populates="group", cascade="all, delete-orphan"
    )


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Stored in cents
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    expense_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC),
        nullable=False,
    )

    # Relationships
    group: Mapped[Group] = relationship("Group", back_populates="expenses")
    payers: Mapped[list[ExpensePayer]] = relationship(
        "ExpensePayer", back_populates="expense", cascade="all, delete-orphan"
    )
    splits: Mapped[list[ExpenseSplit]] = relationship(
        "ExpenseSplit", back_populates="expense", cascade="all, delete-orphan"
    )

    @property
    def payer(self) -> User | None:
        """Single payer convenience property (None if multiple or no payers)."""
        if self.payers and len(self.payers) == 1:
            return self.payers[0].user
        return None

    @property
    def payer_id(self) -> int | None:
        """Single payer ID convenience property (None if multiple or no payers)."""
        if self.payers and len(self.payers) == 1:
            return self.payers[0].user_id
        return None


class ExpensePayer(Base):
    __tablename__ = "expense_payers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("expenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Stored in cents

    # Relationships
    expense: Mapped[Expense] = relationship("Expense", back_populates="payers")
    user: Mapped[User] = relationship("User", back_populates="expense_contributions")


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("expenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Stored in cents

    # Relationships
    expense: Mapped[Expense] = relationship("Expense", back_populates="splits")
    user: Mapped[User] = relationship("User", back_populates="splits")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # Stored in cents
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.UTC),
        nullable=False,
    )

    # Relationships
    group: Mapped[Group] = relationship("Group", back_populates="payments")
    payer: Mapped[User] = relationship(
        "User", foreign_keys=[payer_id], back_populates="payments_sent"
    )
    payee: Mapped[User] = relationship(
        "User", foreign_keys=[payee_id], back_populates="payments_received"
    )
