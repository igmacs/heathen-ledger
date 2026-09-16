import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from tests.base import BaseDatabaseTestCase
from heathen_ledger import crud
from heathen_ledger.dto import ParsedPayCommand, ParsedPaybackCommand, SplitSpec
from heathen_ledger.services import (
    expense_service,
    settlement_service,
    MemberRegistrationService,
)
from heathen_ledger.services.exceptions import (
    UserNotFoundError,
    PermissionDeniedError,
)
from heathen_ledger.commands import CommandDispatcher
from heathen_ledger.keyboards import (
    SettlementKeyboardBuilder,
    HistoryKeyboardBuilder,
    VoiceKeyboardBuilder,
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

    def test_command_dispatcher_pay_and_payback(self):
        # Dispatch /pay
        text, markup = CommandDispatcher.execute(
            command_str="/pay 30 for Lunch",
            chat_id=self.group.telegram_chat_id,
            creator_id=self.alice.telegram_id,
            creator_username=self.alice.username,
            creator_first_name=self.alice.first_name,
            session=self.session,
        )
        self.assertIn("Recorded expense", text)
        self.assertIn("$30.00", text)
        self.assertIsNotNone(markup)

        # Dispatch /payback
        text_pb, markup_pb = CommandDispatcher.execute(
            command_str="/payback @alice 10",
            chat_id=self.group.telegram_chat_id,
            creator_id=self.bob.telegram_id,
            creator_username=self.bob.username,
            creator_first_name=self.bob.first_name,
            session=self.session,
        )
        self.assertIn("Recorded payment", text_pb)
        self.assertIn("$10.00", text_pb)
        self.assertIsNotNone(markup_pb)

        # Dispatch /balances
        text_bal, markup_bal = CommandDispatcher.execute(
            command_str="/balances",
            chat_id=self.group.telegram_chat_id,
            creator_id=self.alice.telegram_id,
            creator_username=self.alice.username,
            creator_first_name=self.alice.first_name,
            session=self.session,
        )
        self.assertIn("Current Net Balances", text_bal)
        self.assertIsNone(markup_bal)

    def test_keyboard_builders(self):
        # VoiceKeyboardBuilder
        kb_v = VoiceKeyboardBuilder.build_confirmation_keyboard("tok123")
        self.assertEqual(len(kb_v.inline_keyboard), 1)
        self.assertEqual(len(kb_v.inline_keyboard[0]), 2)
        self.assertEqual(
            kb_v.inline_keyboard[0][0].callback_data, "voice:confirm:tok123"
        )

        # SettlementKeyboardBuilder empty
        self.assertIsNone(SettlementKeyboardBuilder.build_settle_keyboard([], {}))

        # HistoryKeyboardBuilder empty
        self.assertIsNone(HistoryKeyboardBuilder.build_history_keyboard([]))

    def test_member_registration_service(self):
        from unittest.mock import MagicMock

        # 1. register_reply_user
        bot_user = MagicMock(is_bot=True)
        ok, msg = MemberRegistrationService.register_reply_user(
            self.session, self.group, bot_user
        )
        self.assertFalse(ok)
        self.assertIn("Cannot register a bot", msg)

        # Existing user
        alice_tg = MagicMock(
            id=self.alice.telegram_id,
            username="alice",
            first_name="Alice",
            is_bot=False,
        )
        ok, msg = MemberRegistrationService.register_reply_user(
            self.session, self.group, alice_tg
        )
        self.assertTrue(ok)
        self.assertIn("already registered", msg)

        # New user
        dave_tg = MagicMock(id=999, username="dave", first_name="Dave", is_bot=False)
        ok, msg = MemberRegistrationService.register_reply_user(
            self.session, self.group, dave_tg
        )
        self.assertTrue(ok)
        self.assertIn("Registered member", msg)

        # 2. register_text_mentions
        tm_bot = MagicMock(user=MagicMock(is_bot=True))
        tm_alice = MagicMock(user=alice_tg)
        eve_tg = MagicMock(id=1000, username="eve", first_name="Eve", is_bot=False)
        tm_eve = MagicMock(user=eve_tg)
        reg, already = MemberRegistrationService.register_text_mentions(
            self.session, self.group, [tm_bot, tm_alice, tm_eve]
        )
        self.assertIn("Eve", reg)
        self.assertIn("Alice", already)

        # 3. register_mentions
        admin_frank = MagicMock(
            id=1001, username="frank", first_name="Frank", is_bot=False
        )
        reg_m, already_m = MemberRegistrationService.register_mentions(
            self.session,
            self.group,
            ["alice", "frank", "george"],
            {"frank": admin_frank},
        )
        self.assertIn("@alice", already_m)
        self.assertIn("@frank", reg_m)
        self.assertIn("@george", reg_m)

        # 4. register_handle
        msg_already = MemberRegistrationService.register_handle(
            self.session, self.group, "alice", "Alice", None
        )
        self.assertIn("already registered", msg_already)

        admin_helen = MagicMock(
            id=1002, username="helen", first_name="Helen", is_bot=False
        )
        msg_admin = MemberRegistrationService.register_handle(
            self.session, self.group, "helen", "Helen", admin_helen
        )
        self.assertIn("Registered member *Helen*", msg_admin)

        msg_ext = MemberRegistrationService.register_handle(
            self.session, self.group, "ian", "Ian", None
        )
        self.assertIn("Registered *Ian*", msg_ext)

        # 5. register_name
        ok_name, msg_name = MemberRegistrationService.register_name(
            self.session, self.group, "Jack Sparrow"
        )
        self.assertTrue(ok_name)
        self.assertIn("Jack Sparrow", msg_name)

        ok_inv, msg_inv = MemberRegistrationService.register_name(
            self.session, self.group, "???"
        )
        self.assertFalse(ok_inv)
        self.assertIn("Invalid handle or name", msg_inv)


if __name__ == "__main__":
    unittest.main()
