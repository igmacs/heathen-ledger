import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from tests.base import BaseDatabaseTestCase
from heathen_ledger import crud
from heathen_ledger.dto import ParsedPayCommand, ParsedPaybackCommand, SplitSpec
from heathen_ledger.services import expense_service, settlement_service
from heathen_ledger.services.exceptions import (
    UserNotFoundError,
    PermissionDeniedError,
)


class TestServices(BaseDatabaseTestCase):
    def test_record_expense_equal_all(self):
        cmd = ParsedPayCommand(
            amount=3000,
            payers={"me": 3000},
            description="Dinner",
            split_spec=SplitSpec(mode="all"),
        )
        expense = expense_service.record_expense(
            session=self.session,
            group=self.group,
            sender=self.alice,
            command=cmd,
        )
        self.session.commit()

        self.assertEqual(expense.amount, 3000)
        self.assertEqual(len(expense.splits), 3)
        self.assertEqual({s.amount for s in expense.splits}, {1000})

    def test_record_expense_unknown_user_raises(self):
        cmd = ParsedPayCommand(
            amount=2000,
            payers={"nonexistent": 2000},
            split_spec=SplitSpec(mode="all"),
        )
        with self.assertRaises(UserNotFoundError):
            expense_service.record_expense(
                session=self.session,
                group=self.group,
                sender=self.alice,
                command=cmd,
            )

    def test_toggle_split_participant(self):
        cmd = ParsedPayCommand(
            amount=3000,
            payers={"me": 3000},
            description="Lunch",
            split_spec=SplitSpec(mode="all"),
        )
        expense = expense_service.record_expense(
            session=self.session,
            group=self.group,
            sender=self.alice,
            command=cmd,
        )
        self.session.commit()

        # Alice toggles Charlie out of the split -> should split 1500 each between Alice and Bob
        updated = expense_service.toggle_split_participant(
            session=self.session,
            expense_id=expense.id,
            target_user_id=self.charlie.id,
            clicking_user=self.alice,
            creator_id=self.alice.id,
        )
        self.assertEqual(len(updated.splits), 2)
        split_users = {s.user_id for s in updated.splits}
        self.assertNotIn(self.charlie.id, split_users)
        self.assertEqual({s.amount for s in updated.splits}, {1500})

        # Unauthorized user toggling -> raises PermissionDeniedError
        with self.assertRaises(PermissionDeniedError):
            expense_service.toggle_split_participant(
                session=self.session,
                expense_id=expense.id,
                target_user_id=self.bob.id,
                clicking_user=self.bob,
                creator_id=self.alice.id,
            )

    def test_record_payback_and_undo(self):
        cmd = ParsedPaybackCommand(
            payer_username=None,  # default to sender
            payee_username="alice",
            amount=1500,
        )
        payment = expense_service.record_payback(
            session=self.session,
            group=self.group,
            sender=self.bob,
            command=cmd,
        )
        self.session.commit()

        self.assertEqual(payment.amount, 1500)
        self.assertEqual(payment.payer_id, self.bob.id)
        self.assertEqual(payment.payee_id, self.alice.id)

        # Undo payment by creator (Bob)
        desc = expense_service.undo_transaction(
            session=self.session,
            tx_type="payment",
            tx_id=payment.id,
            clicking_user=self.bob,
            creator_id=self.bob.id,
        )
        self.session.commit()
        self.assertIn("15.00", desc)
        self.assertEqual(len(crud.get_group_payments(self.session, self.group.id)), 0)

    def test_settlement_service(self):
        # Alice paid 20.00 for Alice and Bob (10.00 each)
        splits = {self.alice.id: 1000, self.bob.id: 1000}
        crud.create_expense(
            self.session,
            group_id=self.group.id,
            payer_id=self.alice.id,
            amount=2000,
            splits=splits,
        )
        self.session.commit()

        balances, txs, users_by_id = (
            settlement_service.get_group_balances_and_settlements(
                self.session, self.group.id
            )
        )
        self.assertEqual(balances[self.alice.id], 1000)
        self.assertEqual(balances[self.bob.id], -1000)
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0]["from_user_id"], self.bob.id)
        self.assertEqual(txs[0]["to_user_id"], self.alice.id)

        # Bob confirms settlement payment
        payment = settlement_service.record_settlement_payment(
            session=self.session,
            group=self.group,
            clicking_user=self.bob,
            from_id=self.bob.id,
            to_id=self.alice.id,
            amount=1000,
        )
        self.session.commit()
        self.assertEqual(payment.amount, 1000)

        # Balances should now be 0
        new_balances, new_txs, _ = (
            settlement_service.get_group_balances_and_settlements(
                self.session, self.group.id
            )
        )
        self.assertEqual(new_balances[self.alice.id], 0)
        self.assertEqual(new_balances[self.bob.id], 0)
        self.assertEqual(len(new_txs), 0)


if __name__ == "__main__":
    unittest.main()
