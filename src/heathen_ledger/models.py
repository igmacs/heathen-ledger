import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    BigInteger,
    ForeignKey,
    DateTime,
    Date,
    Table,
    Boolean,
)
from sqlalchemy.orm import relationship

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

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=True, index=True)
    username = Column(String, nullable=True, index=True)
    first_name = Column(String, nullable=False)
    is_external = Column(Boolean, default=False, nullable=False)

    # Relationships
    groups = relationship("Group", secondary=group_members, back_populates="members")
    expenses_paid = relationship("Expense", back_populates="payer")
    expense_contributions = relationship("ExpensePayer", back_populates="user")
    splits = relationship("ExpenseSplit", back_populates="user")
    payments_sent = relationship(
        "Payment", foreign_keys="Payment.payer_id", back_populates="payer"
    )
    payments_received = relationship(
        "Payment", foreign_keys="Payment.payee_id", back_populates="payee"
    )


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    telegram_chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    title = Column(String, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=True,
    )

    # Relationships
    members = relationship("User", secondary=group_members, back_populates="groups")
    expenses = relationship(
        "Expense", back_populates="group", cascade="all, delete-orphan"
    )
    payments = relationship(
        "Payment", back_populates="group", cascade="all, delete-orphan"
    )


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True)
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payer_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    amount = Column(Integer, nullable=False)  # Stored in cents
    description = Column(String, nullable=True)
    expense_date = Column(Date, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Relationships
    group = relationship("Group", back_populates="expenses")
    payer = relationship(
        "User", foreign_keys=[payer_id], back_populates="expenses_paid"
    )
    payers = relationship(
        "ExpensePayer", back_populates="expense", cascade="all, delete-orphan"
    )
    splits = relationship(
        "ExpenseSplit", back_populates="expense", cascade="all, delete-orphan"
    )


class ExpensePayer(Base):
    __tablename__ = "expense_payers"

    id = Column(Integer, primary_key=True)
    expense_id = Column(
        Integer,
        ForeignKey("expenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount = Column(Integer, nullable=False)  # Stored in cents

    # Relationships
    expense = relationship("Expense", back_populates="payers")
    user = relationship("User", back_populates="expense_contributions")


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"

    id = Column(Integer, primary_key=True)
    expense_id = Column(
        Integer,
        ForeignKey("expenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount = Column(Integer, nullable=False)  # Stored in cents

    # Relationships
    expense = relationship("Expense", back_populates="splits")
    user = relationship("User", back_populates="splits")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    group_id = Column(
        Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payer_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payee_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount = Column(Integer, nullable=False)  # Stored in cents
    created_at = Column(
        DateTime,
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )

    # Relationships
    group = relationship("Group", back_populates="payments")
    payer = relationship(
        "User", foreign_keys=[payer_id], back_populates="payments_sent"
    )
    payee = relationship(
        "User", foreign_keys=[payee_id], back_populates="payments_received"
    )
