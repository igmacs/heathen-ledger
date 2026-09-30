import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger import crud
from heathen_ledger.commands import CommandDispatcher
from heathen_ledger.dto import ParsedPaybackCommand, ParsedPayCommand, SplitSpec
from heathen_ledger.keyboards import (
    HistoryKeyboardBuilder,
    SettlementKeyboardBuilder,
    VoiceKeyboardBuilder,
)
from heathen_ledger.services import (
    HistoryService,
    MemberRegistrationService,
    VoiceService,
    expense_service,
    settlement_service,
)
from heathen_ledger.services.exceptions import (
    PermissionDeniedError,
    UserNotFoundError,
    ValidationError,
)

from tests.base import BaseDatabaseTestCase


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

        from heathen_ledger.handlers.registration import (
            format_batch_registration_result,
            format_registration_result,
        )

        # 1. register_user with bot
        bot_user = MagicMock(is_bot=True)
        res_bot = MemberRegistrationService.register_user(
            self.session, self.group, bot_user
        )
        self.assertFalse(res_bot.success)
        self.assertEqual(res_bot.error, "Cannot register a bot.")
        self.assertIn("Cannot register a bot", format_registration_result(res_bot))

        # 2. Existing user
        alice_tg = MagicMock(
            id=self.alice.telegram_id,
            username="alice",
            first_name="Alice",
            is_bot=False,
        )
        res_alice = MemberRegistrationService.register_user(
            self.session, self.group, alice_tg
        )
        self.assertTrue(res_alice.success)
        self.assertTrue(res_alice.already_registered)
        self.assertIn("already registered", format_registration_result(res_alice))

        # 3. New Telegram user
        dave_tg = MagicMock(id=999, username="dave", first_name="Dave", is_bot=False)
        res_dave = MemberRegistrationService.register_user(
            self.session, self.group, dave_tg
        )
        self.assertTrue(res_dave.success)
        self.assertFalse(res_dave.already_registered)
        self.assertEqual(res_dave.user.first_name, "Dave")
        self.assertIn("Registered member", format_registration_result(res_dave))

        # 4. register_users with multiple Telegram users
        eve_tg = MagicMock(id=1000, username="eve", first_name="Eve", is_bot=False)
        batch = MemberRegistrationService.register_users(
            self.session, self.group, [bot_user, alice_tg, eve_tg]
        )
        self.assertEqual(len(batch.registered), 1)
        self.assertEqual(batch.registered[0].first_name, "Eve")
        self.assertEqual(len(batch.already_registered), 1)
        self.assertEqual(batch.already_registered[0].first_name, "Alice")
        msg_batch = format_batch_registration_result(batch)
        self.assertIn("Eve", msg_batch)
        self.assertIn("Alice", msg_batch)

        # 5. register_users with @mentions
        batch_m = MemberRegistrationService.register_users(
            self.session,
            self.group,
            ["@alice", "@frank", "@george"],
        )
        self.assertEqual(len(batch_m.already_registered), 1)
        self.assertEqual(len(batch_m.registered), 2)
        msg_m = format_batch_registration_result(batch_m)
        self.assertIn("@alice", msg_m)
        self.assertIn("@frank", msg_m)
        self.assertIn("@george", msg_m)

        # 6. register_user with handle (already registered)
        res_h_already = MemberRegistrationService.register_user(
            self.session, self.group, "@alice", first_name="Alice"
        )
        self.assertTrue(res_h_already.already_registered)
        self.assertIn("already registered", format_registration_result(res_h_already))

        # 7. Existing global user
        crud.get_or_create_user(
            self.session, telegram_id=1002, username="helen", first_name="Helen"
        )
        self.session.commit()
        res_global = MemberRegistrationService.register_user(
            self.session, self.group, "@helen", first_name="Helen"
        )
        self.assertTrue(res_global.success)
        self.assertFalse(res_global.user.is_external)
        self.assertIn(
            "Registered member *Helen*", format_registration_result(res_global)
        )

        # 8. External / pending user with handle
        res_ext = MemberRegistrationService.register_user(
            self.session, self.group, "@ian", first_name="Ian"
        )
        self.assertTrue(res_ext.success)
        self.assertTrue(res_ext.user.is_external)
        self.assertIn("Registered *Ian*", format_registration_result(res_ext))

        # 9. Register plain name
        res_name = MemberRegistrationService.register_user(
            self.session, self.group, "Jack Sparrow"
        )
        self.assertTrue(res_name.success)
        self.assertEqual(res_name.user.first_name, "Jack Sparrow")
        self.assertIn("Jack Sparrow", format_registration_result(res_name))

        # 10. Register invalid name
        res_inv = MemberRegistrationService.register_user(
            self.session, self.group, "???"
        )
        self.assertFalse(res_inv.success)
        self.assertIn("Invalid handle or name", res_inv.error)
        self.assertIn("Invalid handle or name", format_registration_result(res_inv))

        # 11. Register with Telegram ID integer and chat ID integer
        res_auto = MemberRegistrationService.register_user(
            self.session,
            group=-1008888,
            target=8888,
            username="auto_user",
            first_name="Auto",
            chat_title="Auto Group",
        )
        self.assertEqual(res_auto.user.telegram_id, 8888)
        self.assertEqual(res_auto.group.telegram_chat_id, -1008888)
        self.assertIn(res_auto.user, res_auto.group.members)

        # 12. get_group_members
        members = MemberRegistrationService.get_group_members(
            self.session, self.group.telegram_chat_id
        )
        self.assertIsNotNone(members)
        self.assertTrue(len(members) >= 3)

    def test_history_service(self):
        # 1. Create an expense and a payment
        exp = crud.create_expense(
            self.session,
            group_id=self.group.id,
            payer_id=self.alice.id,
            amount=2000,
            description="Groceries",
            splits={self.alice.id: 1000, self.bob.id: 1000},
        )
        pay = crud.create_payment(
            self.session,
            group_id=self.group.id,
            payer_id=self.bob.id,
            payee_id=self.alice.id,
            amount=500,
        )
        self.session.commit()

        # Query recent transactions
        txs = HistoryService.get_recent_transactions(self.session, self.group.id)
        self.assertEqual(len(txs), 2)
        tx_types = {t["type"] for t in txs}
        self.assertEqual(tx_types, {"expense", "payment"})

        # Unauthorized deletion of expense by Bob -> raises PermissionDeniedError
        with self.assertRaises(PermissionDeniedError):
            HistoryService.delete_transaction(
                self.session, "expense", exp.id, clicking_user=self.bob
            )

        # Unauthorized deletion of payment by Charlie -> raises PermissionDeniedError
        with self.assertRaises(PermissionDeniedError):
            HistoryService.delete_transaction(
                self.session, "payment", pay.id, clicking_user=self.charlie
            )

        # Authorized deletion of expense by Alice
        msg_exp = HistoryService.delete_transaction(
            self.session, "expense", exp.id, clicking_user=self.alice
        )
        self.assertEqual(msg_exp, "Expense deleted.")

        # Authorized deletion of payment by Bob
        msg_pay = HistoryService.delete_transaction(
            self.session, "payment", pay.id, clicking_user=self.bob
        )
        self.assertEqual(msg_pay, "Payment deleted.")

        # Deleting non-existent transaction -> raises ValidationError
        with self.assertRaises(ValidationError):
            HistoryService.delete_transaction(
                self.session, "expense", 99999, clicking_user=self.alice
            )

    def test_voice_service(self):
        # Store pending command
        token = VoiceService.store_pending_command(
            command="/pay 15 for Pizza",
            creator_id=self.alice.telegram_id,
            creator_username=self.alice.username,
            creator_first_name=self.alice.first_name,
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="pay 15 for pizza",
        )
        self.assertIsNotNone(token)

        # Retrieve command
        pending = VoiceService.get_pending_command(token)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.command, "/pay 15 for Pizza")

        # Execute confirmed command
        text, markup = VoiceService.execute_confirmed_command(
            command_str=pending.command,
            chat_id=pending.chat_id,
            creator_id=self.alice.telegram_id,
            creator_username=self.alice.username,
            creator_first_name=self.alice.first_name,
            session=self.session,
        )
        self.assertIn("Recorded expense", text)
        self.assertIsNotNone(markup)

        # Pop pending command
        popped = VoiceService.pop_pending_command(token)
        self.assertEqual(popped, pending)
        self.assertIsNone(VoiceService.get_pending_command(token))

        # Clear store
        VoiceService.store_pending_command(
            command="/balances",
            creator_id=1,
            creator_username=None,
            creator_first_name="User",
            authorized_user_ids={1},
            chat_id=self.group.telegram_chat_id,
            transcription="balances",
        )
        VoiceService.clear_pending_commands()
        self.assertEqual(len(VoiceService.get_store()._commands), 0)


if __name__ == "__main__":
    unittest.main()
