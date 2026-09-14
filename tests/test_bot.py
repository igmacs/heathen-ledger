"""Integration tests for Telegram bot command and callback handlers."""

import sys
import os
import unittest
import asyncio
import datetime
from unittest.mock import AsyncMock, MagicMock
from telegram.error import BadRequest

# Add project src to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from tests.base import BaseDatabaseTestCase
from telegram.constants import MessageEntityType
from heathen_ledger import crud
from heathen_ledger.handlers.base import (
    register_command,
    members_command,
    register_callback_handler,
)
from heathen_ledger.handlers.settle import settle_callback_handler
from heathen_ledger.handlers.expense import (
    undo_callback_handler,
    pay_toggle_callback_handler,
    pay_command,
    payback_command,
)
from heathen_ledger.handlers.history import history_delete_callback_handler
from heathen_ledger.handlers.common import dismiss_callback_handler


class TestSettleCallback(BaseDatabaseTestCase):
    def setUp(self):
        super().setUp()
        # Alice paid $30.00 for all 3 (split is 10.00 each)
        splits = {self.alice.id: 1000, self.bob.id: 1000, self.charlie.id: 1000}
        crud.create_expense(
            self.db_session,
            group_id=self.group.id,
            payer_id=self.alice.id,
            amount=3000,
            description="Test Expense",
            splits=splits,
        )
        self.db_session.commit()

    async def run_settle_callback(self, update):
        context = MagicMock()
        await settle_callback_handler(update, context)

    def test_callback_security_unauthorized_user(self):
        callback_data = f"settle:{self.bob.id}:{self.alice.id}:1000"
        update = self.create_mock_update(
            telegram_user_id=33, callback_data=callback_data
        )
        asyncio.run(self.run_settle_callback(update))

        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Only Bob or Alice can confirm", kwargs.get("text"))

        payments = crud.get_group_payments(self.db_session, self.group.id)
        self.assertEqual(len(payments), 0)

    def test_callback_authorized_payer(self):
        callback_data = f"settle:{self.bob.id}:{self.alice.id}:1000"
        update = self.create_mock_update(
            telegram_user_id=22, callback_data=callback_data
        )
        asyncio.run(self.run_settle_callback(update))

        payments = crud.get_group_payments(self.db_session, self.group.id)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0].payer_id, self.bob.id)
        self.assertEqual(payments[0].payee_id, self.alice.id)
        self.assertEqual(payments[0].amount, 1000)

        update.callback_query.answer.assert_called_once()
        self.assertIn(
            "Recorded: Bob paid Alice",
            update.callback_query.answer.call_args.kwargs.get("text"),
        )
        update.callback_query.edit_message_text.assert_called_once()

    def test_callback_authorized_payee(self):
        callback_data = f"settle:{self.bob.id}:{self.alice.id}:1000"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )
        asyncio.run(self.run_settle_callback(update))

        payments = crud.get_group_payments(self.db_session, self.group.id)
        self.assertEqual(len(payments), 1)
        update.callback_query.edit_message_text.assert_called_once()

    def test_settle_callback_both_external(self):
        john = crud.create_external_user(self.db_session, self.group, "John", "john")
        mary = crud.create_external_user(self.db_session, self.group, "Mary", "mary")
        self.db_session.commit()

        update = self.create_mock_update(
            telegram_user_id=11, callback_data=f"settle:{john.id}:{mary.id}:1000"
        )
        context = MagicMock()
        asyncio.run(settle_callback_handler(update, context))

        payments = crud.get_group_payments(self.db_session, self.group.id)
        matching = [
            p for p in payments if p.payer_id == john.id and p.payee_id == mary.id
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].amount, 1000)


class TestUndoCallback(BaseDatabaseTestCase):
    def setUp(self):
        super().setUp()
        splits = {self.alice.id: 1000, self.bob.id: 1000, self.charlie.id: 1000}
        crud.create_expense(
            self.db_session,
            group_id=self.group.id,
            payer_id=self.alice.id,
            amount=3000,
            description="Test Expense",
            splits=splits,
        )
        self.db_session.commit()

    async def run_undo_callback(self, update):
        context = MagicMock()
        await undo_callback_handler(update, context)

    def test_undo_security_unauthorized_user(self):
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"undo:expense:{expense.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=33, callback_data=callback_data
        )
        asyncio.run(self.run_undo_callback(update))

        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Only Alice can undo", kwargs.get("text"))
        self.assertEqual(
            len(crud.get_group_expenses(self.db_session, self.group.id)), 1
        )

    def test_undo_authorized_creator_expense(self):
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"undo:expense:{expense.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )
        asyncio.run(self.run_undo_callback(update))

        self.assertEqual(
            len(crud.get_group_expenses(self.db_session, self.group.id)), 0
        )
        update.callback_query.answer.assert_called_once_with(text="Transaction undone.")
        update.callback_query.edit_message_text.assert_called_once()
        kwargs = update.callback_query.edit_message_text.call_args.kwargs
        self.assertIn("has been undone by Alice", kwargs.get("text"))

    def test_undo_authorized_creator_payment(self):
        payment = crud.create_payment(
            self.db_session, self.group.id, self.bob.id, self.alice.id, 500
        )
        self.db_session.commit()

        callback_data = f"undo:payment:{payment.id}:{self.bob.id}"
        update = self.create_mock_update(
            telegram_user_id=22, callback_data=callback_data
        )
        asyncio.run(self.run_undo_callback(update))

        self.assertEqual(
            len(crud.get_group_payments(self.db_session, self.group.id)), 0
        )
        update.callback_query.answer.assert_called_once_with(text="Transaction undone.")
        update.callback_query.edit_message_text.assert_called_once()
        kwargs = update.callback_query.edit_message_text.call_args.kwargs
        self.assertIn("has been undone by Bob", kwargs.get("text"))


class TestHistoryDeleteCallback(BaseDatabaseTestCase):
    def setUp(self):
        super().setUp()
        splits = {self.alice.id: 1000, self.bob.id: 1000, self.charlie.id: 1000}
        crud.create_expense(
            self.db_session,
            group_id=self.group.id,
            payer_id=self.alice.id,
            amount=3000,
            description="Test Expense",
            splits=splits,
        )
        self.db_session.commit()

    async def run_history_delete_callback(self, update):
        context = MagicMock()
        await history_delete_callback_handler(update, context)

    def test_history_delete_security_unauthorized_user(self):
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"hist_del:expense:{expense.id}"
        update = self.create_mock_update(
            telegram_user_id=33, callback_data=callback_data
        )
        asyncio.run(self.run_history_delete_callback(update))

        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Only Alice can delete", kwargs.get("text"))
        self.assertEqual(
            len(crud.get_group_expenses(self.db_session, self.group.id)), 1
        )

    def test_history_delete_authorized_expense(self):
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"hist_del:expense:{expense.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )
        asyncio.run(self.run_history_delete_callback(update))

        self.assertEqual(
            len(crud.get_group_expenses(self.db_session, self.group.id)), 0
        )
        update.callback_query.answer.assert_called_once_with(text="Expense deleted.")
        update.callback_query.edit_message_text.assert_called_once()

    def test_history_delete_authorized_payment(self):
        payment = crud.create_payment(
            self.db_session, self.group.id, self.bob.id, self.alice.id, 500
        )
        self.db_session.commit()

        callback_data = f"hist_del:payment:{payment.id}"
        update = self.create_mock_update(
            telegram_user_id=22, callback_data=callback_data
        )
        asyncio.run(self.run_history_delete_callback(update))

        self.assertEqual(
            len(crud.get_group_payments(self.db_session, self.group.id)), 0
        )
        update.callback_query.answer.assert_called_once_with(text="Payment deleted.")
        update.callback_query.edit_message_text.assert_called_once()


class TestDismissCallback(BaseDatabaseTestCase):
    async def run_dismiss_callback(self, update):
        context = MagicMock()
        await dismiss_callback_handler(update, context)

    def test_dismiss_callback(self):
        update = self.create_mock_update(telegram_user_id=11, callback_data="dismiss")
        reply_to_mock = AsyncMock()
        update.callback_query.message.reply_to_message = reply_to_mock

        asyncio.run(self.run_dismiss_callback(update))

        reply_to_mock.delete.assert_called_once()
        update.callback_query.message.delete.assert_called_once()
        update.callback_query.answer.assert_called_once()

    def test_dismiss_callback_bad_request(self):
        update = self.create_mock_update(telegram_user_id=11, callback_data="dismiss")
        reply_to_mock = AsyncMock()
        reply_to_mock.delete.side_effect = BadRequest("Cannot delete user message")
        update.callback_query.message.reply_to_message = reply_to_mock

        update.callback_query.message.delete.side_effect = BadRequest(
            "Message to delete not found"
        )
        asyncio.run(self.run_dismiss_callback(update))

        reply_to_mock.delete.assert_called_once()
        update.callback_query.message.delete.assert_called_once()
        update.callback_query.answer.assert_called_once()


class TestPayToggleCallback(BaseDatabaseTestCase):
    def setUp(self):
        super().setUp()
        splits = {self.alice.id: 1000, self.bob.id: 1000, self.charlie.id: 1000}
        crud.create_expense(
            self.db_session,
            group_id=self.group.id,
            payer_id=self.alice.id,
            amount=3000,
            description="Test Expense",
            splits=splits,
        )
        self.db_session.commit()

    async def run_pay_toggle_callback(self, update):
        context = MagicMock()
        await pay_toggle_callback_handler(update, context)

    def test_pay_toggle_security_unauthorized_user(self):
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"pay_toggle:{expense.id}:{self.bob.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=33, callback_data=callback_data
        )
        asyncio.run(self.run_pay_toggle_callback(update))

        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Only Alice can edit", kwargs.get("text"))

    def test_pay_toggle_remove_participant(self):
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        self.assertEqual(len(expense.splits), 3)

        callback_data = f"pay_toggle:{expense.id}:{self.bob.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )
        asyncio.run(self.run_pay_toggle_callback(update))

        self.db_session.expire_all()
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        self.assertEqual(len(expense.splits), 2)

        splits_dict = {s.user_id: s.amount for s in expense.splits}
        self.assertNotIn(self.bob.id, splits_dict)
        self.assertEqual(splits_dict[self.alice.id], 1500)
        self.assertEqual(splits_dict[self.charlie.id], 1500)

        update.callback_query.edit_message_text.assert_called_once()
        kwargs = update.callback_query.edit_message_text.call_args.kwargs
        self.assertIn("Alice: $15.00", kwargs.get("text"))
        self.assertIn("Charlie: $15.00", kwargs.get("text"))
        self.assertNotIn("Bob:", kwargs.get("text"))

    def test_pay_toggle_add_participant(self):
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        for split in list(expense.splits):
            if split.user_id == self.bob.id:
                self.db_session.delete(split)
        self.db_session.commit()

        callback_data = f"pay_toggle:{expense.id}:{self.bob.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )
        asyncio.run(self.run_pay_toggle_callback(update))

        self.db_session.expire_all()
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        self.assertEqual(len(expense.splits), 3)

        splits_dict = {s.user_id: s.amount for s in expense.splits}
        self.assertEqual(splits_dict[self.bob.id], 1000)
        self.assertEqual(splits_dict[self.alice.id], 1000)
        self.assertEqual(splits_dict[self.charlie.id], 1000)

    def test_pay_toggle_prevent_removing_last_participant(self):
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        for split in list(expense.splits):
            if split.user_id != self.alice.id:
                self.db_session.delete(split)
        expense.splits[0].amount = 3000
        self.db_session.commit()

        callback_data = f"pay_toggle:{expense.id}:{self.alice.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )
        asyncio.run(self.run_pay_toggle_callback(update))

        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Cannot remove the last participant", kwargs.get("text"))

        self.db_session.expire_all()
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        self.assertEqual(len(expense.splits), 1)
        self.assertEqual(expense.splits[0].user_id, self.alice.id)


class TestPayCommandHandler(BaseDatabaseTestCase):
    def test_pay_command_multi_payer_equal(self):
        update = self.create_mock_message_update("/pay 90 for Dinner by me @Bob")
        context = MagicMock()
        asyncio.run(pay_command(update, context))

        expenses = crud.get_group_expenses(self.db_session, self.group.id)
        self.assertEqual(len(expenses), 1)
        exp = expenses[0]
        self.assertEqual(exp.amount, 9000)
        self.assertEqual(len(exp.payers), 2)
        payer_map = {p.user_id: p.amount for p in exp.payers}
        self.assertEqual(payer_map[self.alice.id], 4500)
        self.assertEqual(payer_map[self.bob.id], 4500)
        self.assertEqual(len(exp.splits), 3)

        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args.args[0]
        self.assertIn("Alice: $45.00", reply_text)
        self.assertIn("Bob: $45.00", reply_text)

    def test_pay_command_with_date(self):
        update = self.create_mock_message_update("/pay 50 for Lunch on 2026-09-07")
        context = MagicMock()
        asyncio.run(pay_command(update, context))

        expenses = crud.get_group_expenses(self.db_session, self.group.id)
        self.assertEqual(len(expenses), 1)
        exp = expenses[0]
        self.assertEqual(exp.expense_date, datetime.date(2026, 9, 7))

        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args.args[0]
        self.assertIn("**Date:** 2026-09-07", reply_text)

    def test_pay_command_custom_split(self):
        update = self.create_mock_message_update(
            "/pay 30 for drinks split @Bob:10 @Charlie:20"
        )
        context = MagicMock()
        asyncio.run(pay_command(update, context))

        expenses = crud.get_group_expenses(self.db_session, self.group.id)
        self.assertEqual(len(expenses), 1)
        exp = expenses[0]
        self.assertEqual(len(exp.splits), 2)
        splits_map = {s.user_id: s.amount for s in exp.splits}
        self.assertEqual(splits_map[self.bob.id], 1000)
        self.assertEqual(splits_map[self.charlie.id], 2000)

    def test_pay_command_split_except(self):
        update = self.create_mock_message_update(
            "/pay 40 for snacks split except @Charlie"
        )
        context = MagicMock()
        asyncio.run(pay_command(update, context))

        expenses = crud.get_group_expenses(self.db_session, self.group.id)
        self.assertEqual(len(expenses), 1)
        exp = expenses[0]
        self.assertEqual(len(exp.splits), 2)
        splits_map = {s.user_id: s.amount for s in exp.splits}
        self.assertNotIn(self.charlie.id, splits_map)
        self.assertEqual(splits_map[self.alice.id], 2000)
        self.assertEqual(splits_map[self.bob.id], 2000)


class TestRegistrationHandlers(BaseDatabaseTestCase):
    def test_register_command_and_members(self):
        # 1. Empty /register shows registration inline button
        update_empty = self.create_mock_message_update("/register")
        context = MagicMock()
        asyncio.run(register_command(update_empty, context))
        update_empty.message.reply_text.assert_called_once()
        reply_call = update_empty.message.reply_text.call_args
        self.assertIn("Member Registration", reply_call.args[0])
        self.assertIsNotNone(reply_call.kwargs.get("reply_markup"))
        buttons = reply_call.kwargs["reply_markup"].inline_keyboard
        self.assertEqual(buttons[0][0].callback_data, "register:join")

        # 2. Register simple name
        update_reg = self.create_mock_message_update("/register John")
        asyncio.run(register_command(update_reg, context))
        update_reg.message.reply_text.assert_called_once()
        reply = update_reg.message.reply_text.call_args.args[0]
        self.assertIn("Registered external member *John* (`@john`)", reply)

        # 3. Duplicate handle check
        update_dup = self.create_mock_message_update("/register @john John Two")
        asyncio.run(register_command(update_dup, context))
        update_dup.message.reply_text.assert_called_once()
        self.assertIn(
            "already registered", update_dup.message.reply_text.call_args.args[0]
        )

        # 4. Register with explicit handle and full name
        update_reg2 = self.create_mock_message_update("/register @maria_s Maria Silva")
        asyncio.run(register_command(update_reg2, context))
        self.assertIn(
            "Registered *Maria Silva* (`@maria_s`)",
            update_reg2.message.reply_text.call_args.args[0],
        )

        # 5. /members command
        update_mem = self.create_mock_message_update("/members")
        asyncio.run(members_command(update_mem, context))
        mem_reply = update_mem.message.reply_text.call_args.args[0]
        self.assertIn("Alice", mem_reply)
        self.assertIn("John", mem_reply)
        self.assertIn("_[external]_", mem_reply)

        # 6. /pay involving external user
        update_pay = self.create_mock_message_update(
            "/pay 30 for pizza split @john @alice"
        )
        asyncio.run(pay_command(update_pay, context))
        expenses = crud.get_group_expenses(self.db_session, self.group.id)
        latest_exp = expenses[-1]
        self.assertEqual(len(latest_exp.splits), 2)
        john_user = crud.get_user_in_group(self.db_session, self.group.id, "john")
        self.assertIsNotNone(john_user)
        self.assertTrue(john_user.is_external)
        splits_users = {s.user_id for s in latest_exp.splits}
        self.assertIn(john_user.id, splits_users)

        # 7. /payback involving external user
        update_payback = self.create_mock_message_update("/payback @john 15")
        asyncio.run(payback_command(update_payback, context))
        payments = crud.get_group_payments(self.db_session, self.group.id)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0].payer_id, self.alice.id)
        self.assertEqual(payments[0].payee_id, john_user.id)
        self.assertEqual(payments[0].amount, 1500)

    def test_register_inline_button_callback(self):
        context = MagicMock()

        # 1. New user clicks button to register
        update_click = self.create_mock_update(
            telegram_user_id=7777, callback_data="register:join"
        )
        update_click.callback_query.from_user.username = "dave"
        update_click.callback_query.from_user.first_name = "Dave"
        asyncio.run(register_callback_handler(update_click, context))

        update_click.callback_query.answer.assert_called_once()
        self.assertIn(
            "now registered as Dave",
            update_click.callback_query.answer.call_args.args[0],
        )
        update_click.callback_query.message.reply_text.assert_called_once()
        self.assertIn(
            "Dave", update_click.callback_query.message.reply_text.call_args.args[0]
        )

        dave_user = crud.get_user_by_telegram_id(self.db_session, 7777)
        self.assertIsNotNone(dave_user)
        self.assertIn(dave_user, self.group.members)

        # 2. Click again: shows already registered
        update_click_again = self.create_mock_update(
            telegram_user_id=7777, callback_data="register:join"
        )
        update_click_again.callback_query.from_user.username = "dave"
        update_click_again.callback_query.from_user.first_name = "Dave"
        asyncio.run(register_callback_handler(update_click_again, context))
        self.assertIn(
            "already registered",
            update_click_again.callback_query.answer.call_args.args[0],
        )

    def test_register_inline_button_links_external_user(self):
        context = MagicMock()
        # Pre-register external user with handle emily
        ext_user = crud.create_external_user(
            self.db_session, self.group, "Emily", username="emily"
        )
        self.db_session.commit()
        ext_id = ext_user.id

        # Emily taps the inline button
        update_click = self.create_mock_update(
            telegram_user_id=8888, callback_data="register:join"
        )
        update_click.callback_query.from_user.username = "emily"
        update_click.callback_query.from_user.first_name = "Emily Smith"
        asyncio.run(register_callback_handler(update_click, context))

        linked = crud.get_user_by_telegram_id(self.db_session, 8888)
        self.assertIsNotNone(linked)
        self.assertEqual(linked.id, ext_id)
        self.assertFalse(linked.is_external)
        self.assertEqual(linked.first_name, "Emily Smith")

    def test_register_reply_to_message(self):
        context = MagicMock()

        # Reply to a message sent by Frank
        update_reply = self.create_mock_message_update("/register")
        target_user = MagicMock()
        target_user.id = 54321
        target_user.username = "frank"
        target_user.first_name = "Frank"
        target_user.is_bot = False
        reply_msg = MagicMock()
        reply_msg.from_user = target_user
        update_reply.message.reply_to_message = reply_msg

        asyncio.run(register_command(update_reply, context))
        update_reply.message.reply_text.assert_called_once()
        self.assertIn(
            "Registered member *Frank*",
            update_reply.message.reply_text.call_args.args[0],
        )

        frank = crud.get_user_by_telegram_id(self.db_session, 54321)
        self.assertIsNotNone(frank)
        self.assertIn(frank, self.group.members)

        # Replying again says already registered
        update_reply2 = self.create_mock_message_update("/register")
        update_reply2.message.reply_to_message = reply_msg
        asyncio.run(register_command(update_reply2, context))
        self.assertIn(
            "already registered", update_reply2.message.reply_text.call_args.args[0]
        )

    def test_register_text_mention(self):
        context = MagicMock()
        update_tm = self.create_mock_message_update("/register")
        entity = MagicMock()
        entity.type = MessageEntityType.TEXT_MENTION
        target = MagicMock()
        target.id = 67890
        target.username = None
        target.first_name = "Grace"
        target.is_bot = False
        entity.user = target
        update_tm.message.entities = [entity]

        asyncio.run(register_command(update_tm, context))
        update_tm.message.reply_text.assert_called_once()
        self.assertIn(
            "Registered member(s): *Grace*",
            update_tm.message.reply_text.call_args.args[0],
        )

        grace = crud.get_user_by_telegram_id(self.db_session, 67890)
        self.assertIsNotNone(grace)
        self.assertIn(grace, self.group.members)

    def test_register_admin_mention(self):
        context = MagicMock()
        # Mock get_chat_administrators returning admin Harry
        admin_member = MagicMock()
        admin_member.user.id = 99901
        admin_member.user.username = "harry"
        admin_member.user.first_name = "Harry"
        context.bot.get_chat_administrators = AsyncMock(return_value=[admin_member])

        update_adm = self.create_mock_message_update("/register @harry")
        asyncio.run(register_command(update_adm, context))
        update_adm.message.reply_text.assert_called_once()
        self.assertIn(
            "Registered member *Harry* (`@harry`)",
            update_adm.message.reply_text.call_args.args[0],
        )

        harry = crud.get_user_by_telegram_id(self.db_session, 99901)
        self.assertIsNotNone(harry)
        self.assertFalse(harry.is_external)
        self.assertIn(harry, self.group.members)

    def test_register_global_telegram_user_mention(self):
        context = MagicMock()
        context.bot.get_chat_administrators = AsyncMock(return_value=[])

        # Create global Telegram user Iris in DB (not in self.group)
        iris = crud.get_or_create_user(
            self.db_session, 99902, username="iris", first_name="Iris"
        )
        self.db_session.commit()
        self.assertNotIn(iris, self.group.members)

        update_iris = self.create_mock_message_update("/register @iris")
        asyncio.run(register_command(update_iris, context))
        update_iris.message.reply_text.assert_called_once()
        self.assertIn(
            "Registered member *Iris* (`@iris`)",
            update_iris.message.reply_text.call_args.args[0],
        )
        self.assertIn(iris, self.group.members)

    def test_register_multiple_mentions(self):
        context = MagicMock()
        context.bot.get_chat_administrators = AsyncMock(return_value=[])

        update_multi = self.create_mock_message_update("/register @jack @karen")
        asyncio.run(register_command(update_multi, context))
        update_multi.message.reply_text.assert_called_once()
        reply = update_multi.message.reply_text.call_args.args[0]
        self.assertIn("Registered member(s): @jack, @karen", reply)

        jack = crud.get_user_in_group(self.db_session, self.group.id, "jack")
        karen = crud.get_user_in_group(self.db_session, self.group.id, "karen")
        self.assertIsNotNone(jack)
        self.assertIsNotNone(karen)


if __name__ == "__main__":
    unittest.main()
