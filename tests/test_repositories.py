import datetime
import os
import sys
import unittest

# Add project src to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.database import Base
from heathen_ledger.domain import BalanceCalculator
from heathen_ledger.models import ExpensePayer, ExpenseSplit
from heathen_ledger.repositories import (
    ExpenseRepository,
    GroupRepository,
    PaymentRepository,
    UserRepository,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class TestRepositories(unittest.TestCase):
    def test_ledger_scenario(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            group_repo = GroupRepository(session)
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            payment_repo = PaymentRepository(session)

            # 1. Register group and users
            group = group_repo.get_or_create(12345, "Trip to Spain")
            alice = user_repo.get_or_create(11, "alice", "Alice")
            bob = user_repo.get_or_create(22, "bob", "Bob")
            charlie = user_repo.get_or_create(33, "charlie", "Charlie")

            # 2. Add users to group
            user_repo.add_to_group(alice, group)
            user_repo.add_to_group(bob, group)
            user_repo.add_to_group(charlie, group)
            session.commit()

            # Verify membership
            self.assertEqual(len(group.members), 3)

            # 3. Log a split expense
            # Alice paid 30.00 (3000 cents) for dinner, split equally between Alice, Bob, and Charlie (1000 each)
            splits = {alice.id: 1000, bob.id: 1000, charlie.id: 1000}
            exp1 = expense_repo.create(
                group_id=group.id,
                payer_id=alice.id,
                amount=3000,
                description="Dinner",
                splits=splits,
            )
            session.commit()

            self.assertEqual(len(exp1.payers), 1)
            self.assertEqual(exp1.payers[0].user_id, alice.id)
            self.assertEqual(exp1.payer, alice)
            self.assertEqual(exp1.payer_id, alice.id)

            # Verify balances: Alice should be owed 20.00 (+2000), Bob and Charlie owe 10.00 (-1000) each.
            balances = BalanceCalculator.calculate_net_balances(
                members=group.members,
                expenses=expense_repo.get_for_group(group.id),
                payments=payment_repo.get_for_group(group.id),
            )
            self.assertEqual(balances[alice.id], 2000)
            self.assertEqual(balances[bob.id], -1000)
            self.assertEqual(balances[charlie.id], -1000)

            # 4. Log a settlement payment
            # Bob pays Alice 10.00 (1000 cents)
            payment_repo.create(
                group_id=group.id,
                payer_id=bob.id,
                payee_id=alice.id,
                amount=1000,
            )
            session.commit()

            # Verify updated balances: Bob is settled (0), Alice is owed 10.00 (+1000), Charlie owes 10.00 (-1000).
            balances = BalanceCalculator.calculate_net_balances(
                members=group.members,
                expenses=expense_repo.get_for_group(group.id),
                payments=payment_repo.get_for_group(group.id),
            )
            self.assertEqual(balances[alice.id], 1000)
            self.assertEqual(balances[bob.id], 0)
            self.assertEqual(balances[charlie.id], -1000)

            # 5. Retrieve recent transactions history
            history = payment_repo.get_recent_transactions(group.id)
            self.assertEqual(len(history), 2)  # 1 expense and 1 payment
            self.assertEqual(history[0]["type"], "payment")
            self.assertEqual(history[1]["type"], "expense")

    def test_deletion_scenario(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            group_repo = GroupRepository(session)
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)
            payment_repo = PaymentRepository(session)

            group = group_repo.get_or_create(12345, "Trip to Spain")
            alice = user_repo.get_or_create(11, "alice", "Alice")
            bob = user_repo.get_or_create(22, "bob", "Bob")
            user_repo.add_to_group(alice, group)
            user_repo.add_to_group(bob, group)
            session.commit()

            # Create expense
            splits = {alice.id: 500, bob.id: 500}
            expense = expense_repo.create(
                group_id=group.id,
                payer_id=alice.id,
                amount=1000,
                description="Pizza",
                splits=splits,
            )
            session.commit()

            # Create payment
            payment = payment_repo.create(
                group_id=group.id,
                payer_id=bob.id,
                payee_id=alice.id,
                amount=500,
            )
            session.commit()

            # Verify presence
            self.assertEqual(len(expense_repo.get_for_group(group.id)), 1)
            self.assertEqual(len(payment_repo.get_for_group(group.id)), 1)

            # Delete payment
            success_pay = payment_repo.delete(payment.id)
            session.commit()
            self.assertTrue(success_pay)
            self.assertEqual(len(payment_repo.get_for_group(group.id)), 0)

            # Delete expense (should cascade delete splits)
            success_exp = expense_repo.delete(expense.id)
            session.commit()
            self.assertTrue(success_exp)
            self.assertEqual(len(expense_repo.get_for_group(group.id)), 0)

    def test_multi_payer_expense_scenario(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            group_repo = GroupRepository(session)
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)

            group = group_repo.get_or_create(9999, "Vacation")
            alice = user_repo.get_or_create(101, "alice", "Alice")
            bob = user_repo.get_or_create(102, "bob", "Bob")
            charlie = user_repo.get_or_create(103, "charlie", "Charlie")
            user_repo.add_to_group(alice, group)
            user_repo.add_to_group(bob, group)
            user_repo.add_to_group(charlie, group)
            session.commit()

            # Total $60: Alice paid 40 (4000), Bob paid 20 (2000). Split 20 (2000) each.
            exp_date = datetime.date(2026, 9, 7)
            expense = expense_repo.create(
                group_id=group.id,
                amount=6000,
                description="Groceries & Snacks",
                payers={alice.id: 4000, bob.id: 2000},
                splits={alice.id: 2000, bob.id: 2000, charlie.id: 2000},
                expense_date=exp_date,
            )
            session.commit()

            self.assertEqual(len(expense.payers), 2)
            self.assertIsNone(expense.payer)
            self.assertIsNone(expense.payer_id)
            self.assertEqual(expense.expense_date, exp_date)

            balances = BalanceCalculator.calculate_net_balances(
                members=group.members,
                expenses=expense_repo.get_for_group(group.id),
                payments=[],
            )
            self.assertEqual(balances[alice.id], 2000)
            self.assertEqual(balances[bob.id], 0)
            self.assertEqual(balances[charlie.id], -2000)

            # Cascade delete check
            self.assertEqual(session.query(ExpensePayer).count(), 2)
            self.assertEqual(session.query(ExpenseSplit).count(), 3)
            success_exp = expense_repo.delete(expense.id)
            session.commit()
            self.assertTrue(success_exp)
            self.assertEqual(len(expense_repo.get_for_group(group.id)), 0)
            self.assertEqual(session.query(ExpensePayer).count(), 0)
            self.assertEqual(session.query(ExpenseSplit).count(), 0)

    def test_external_user_repositories(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            group_repo = GroupRepository(session)
            user_repo = UserRepository(session)
            expense_repo = ExpenseRepository(session)

            group1 = group_repo.get_or_create(1001, "Flatmates")
            group2 = group_repo.get_or_create(1002, "Hiking Club")

            # Create regular telegram user in group 1
            alice = user_repo.get_or_create(1, "alice", "Alice")
            user_repo.add_to_group(alice, group1)

            # Register external user in group 1
            john = user_repo.create_external(
                group=group1, first_name="John Doe", username="john"
            )
            session.commit()

            self.assertIsNone(john.telegram_id)
            self.assertTrue(john.is_external)
            self.assertEqual(john.username, "john")
            self.assertEqual(john.first_name, "John Doe")
            self.assertIn(john, group1.members)
            self.assertNotIn(john, group2.members)

            # Test get_in_group within group 1
            self.assertEqual(user_repo.get_in_group(group1.id, "john"), john)
            self.assertEqual(user_repo.get_in_group(group1.id, "@john"), john)
            self.assertEqual(user_repo.get_in_group(group1.id, "John Doe"), john)
            self.assertEqual(user_repo.get_in_group(group1.id, "alice"), alice)

            # External user in group 1 must NOT be found from group 2
            self.assertIsNone(user_repo.get_in_group(group2.id, "john"))

            # Expense with external user
            # Alice paid $20, split equally with John ($10 each)
            expense_repo.create(
                group_id=group1.id,
                payer_id=alice.id,
                amount=2000,
                description="Groceries",
                splits={alice.id: 1000, john.id: 1000},
            )
            session.commit()

            balances = BalanceCalculator.calculate_net_balances(
                members=group1.members,
                expenses=expense_repo.get_for_group(group1.id),
                payments=[],
            )
            self.assertEqual(balances[alice.id], 1000)
            self.assertEqual(balances[john.id], -1000)

    def test_link_external_user_on_registration(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            group_repo = GroupRepository(session)
            user_repo = UserRepository(session)

            group = group_repo.get_or_create(12345, "Trip")
            # Register external user John
            ext_john = user_repo.create_external(
                group=group, first_name="John", username="johndoe"
            )
            session.commit()
            self.assertTrue(ext_john.is_external)
            self.assertIsNone(ext_john.telegram_id)
            john_db_id = ext_john.id

            # John now interacts with the bot using Telegram ID 9999 and handle @johndoe
            linked_user = user_repo.get_or_create(
                telegram_id=9999, username="johndoe", first_name="John Doe"
            )
            session.commit()

            # Verify it's the exact same user record upgraded to a Telegram user
            self.assertEqual(linked_user.id, john_db_id)
            self.assertEqual(linked_user.telegram_id, 9999)
            self.assertFalse(linked_user.is_external)
            self.assertEqual(linked_user.first_name, "John Doe")
            self.assertEqual(linked_user.username, "johndoe")
            self.assertIn(linked_user, group.members)

    def test_direct_repository_and_balance_calculator(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            user_repo = UserRepository(session)
            group_repo = GroupRepository(session)
            expense_repo = ExpenseRepository(session)
            payment_repo = PaymentRepository(session)

            group = group_repo.get_or_create(77777, "Trip")
            u1 = user_repo.get_or_create(101, "u1", "User One")
            u2 = user_repo.get_or_create(102, "u2", "User Two")
            user_repo.add_to_group(u1, group)
            user_repo.add_to_group(u2, group)
            session.commit()

            # Create expense: u1 paid 2000, split 1000 each
            exp = expense_repo.create(
                group_id=group.id,
                payer_id=u1.id,
                amount=2000,
                description="Groceries",
                splits={u1.id: 1000, u2.id: 1000},
            )
            session.commit()
            self.assertIsNotNone(exp.id)

            # Test pure balance calculation
            balances = BalanceCalculator.calculate_net_balances(
                members=group.members,
                expenses=[exp],
                payments=[],
            )
            self.assertEqual(balances[u1.id], 1000)
            self.assertEqual(balances[u2.id], -1000)

            # Record payback: u2 pays u1 1000
            pay = payment_repo.create(
                group_id=group.id,
                payer_id=u2.id,
                payee_id=u1.id,
                amount=1000,
            )
            session.commit()

            balances_settled = BalanceCalculator.calculate_net_balances(
                members=group.members,
                expenses=[exp],
                payments=[pay],
            )
            self.assertEqual(balances_settled[u1.id], 0)
            self.assertEqual(balances_settled[u2.id], 0)


if __name__ == "__main__":
    unittest.main()
