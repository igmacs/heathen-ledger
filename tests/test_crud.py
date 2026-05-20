import sys
import os

import unittest

# Add project root to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import crud


class TestCRUD(unittest.TestCase):
    def test_ledger_scenario(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            # 1. Register group and users
            group = crud.get_or_create_group(session, 12345, "Trip to Spain")
            alice = crud.get_or_create_user(session, 11, "alice", "Alice")
            bob = crud.get_or_create_user(session, 22, "bob", "Bob")
            charlie = crud.get_or_create_user(session, 33, "charlie", "Charlie")

            # 2. Add users to group
            crud.add_user_to_group(session, alice, group)
            crud.add_user_to_group(session, bob, group)
            crud.add_user_to_group(session, charlie, group)
            session.commit()

            # Verify membership
            self.assertEqual(len(group.members), 3)

            # 3. Log a split expense
            # Alice paid 30.00 (3000 cents) for dinner, split equally between Alice, Bob, and Charlie (1000 each)
            splits = {alice.id: 1000, bob.id: 1000, charlie.id: 1000}
            crud.create_expense(
                session,
                group_id=group.id,
                payer_id=alice.id,
                amount=3000,
                description="Dinner",
                splits=splits,
            )
            session.commit()

            # Verify balances: Alice should be owed 20.00 (+2000), Bob and Charlie owe 10.00 (-1000) each.
            balances = crud.get_group_balances(session, group.id)
            self.assertEqual(balances[alice.id], 2000)
            self.assertEqual(balances[bob.id], -1000)
            self.assertEqual(balances[charlie.id], -1000)

            # 4. Log a settlement payment
            # Bob pays Alice 10.00 (1000 cents)
            crud.create_payment(
                session,
                group_id=group.id,
                payer_id=bob.id,
                payee_id=alice.id,
                amount=1000,
            )
            session.commit()

            # Verify updated balances: Bob is settled (0), Alice is owed 10.00 (+1000), Charlie owes 10.00 (-1000).
            balances = crud.get_group_balances(session, group.id)
            self.assertEqual(balances[alice.id], 1000)
            self.assertEqual(balances[bob.id], 0)
            self.assertEqual(balances[charlie.id], -1000)

            # 5. Retrieve recent transactions history
            history = crud.get_recent_transactions(session, group.id)
            self.assertEqual(len(history), 2)  # 1 expense and 1 payment
            self.assertEqual(history[0]["type"], "payment")
            self.assertEqual(history[1]["type"], "expense")

    def test_deletion_scenario(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            group = crud.get_or_create_group(session, 12345, "Trip to Spain")
            alice = crud.get_or_create_user(session, 11, "alice", "Alice")
            bob = crud.get_or_create_user(session, 22, "bob", "Bob")
            crud.add_user_to_group(session, alice, group)
            crud.add_user_to_group(session, bob, group)
            session.commit()

            # Create expense
            splits = {alice.id: 500, bob.id: 500}
            expense = crud.create_expense(
                session, group.id, alice.id, 1000, "Pizza", splits
            )
            session.commit()

            # Create payment
            payment = crud.create_payment(session, group.id, bob.id, alice.id, 500)
            session.commit()

            # Verify presence
            self.assertEqual(len(crud.get_group_expenses(session, group.id)), 1)
            self.assertEqual(len(crud.get_group_payments(session, group.id)), 1)

            # Delete payment
            success_pay = crud.delete_payment(session, payment.id)
            session.commit()
            self.assertTrue(success_pay)
            self.assertEqual(len(crud.get_group_payments(session, group.id)), 0)

            # Delete expense (should cascade delete splits)
            success_exp = crud.delete_expense(session, expense.id)
            session.commit()
            self.assertTrue(success_exp)
            self.assertEqual(len(crud.get_group_expenses(session, group.id)), 0)


if __name__ == "__main__":
    unittest.main()
