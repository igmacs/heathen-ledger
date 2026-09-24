"""Unit tests for the /close command: settlement validation, group deletion, and chat departure."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from telegram.constants import ChatType

from tests.base import BaseDatabaseTestCase
from heathen_ledger import crud
from heathen_ledger.models import User
from heathen_ledger.handlers.close import close_command
from heathen_ledger.repositories import GroupRepository, UserRepository


class TestCloseCommand(BaseDatabaseTestCase):
    """Test suite for closing settled ledgers and group reset."""

    def test_close_in_private_chat_blocked(self):
        update = self.create_mock_message_update("/close", chat_id=12345)
        update.effective_chat.type = ChatType.PRIVATE
        context = MagicMock()
        context.bot.leave_chat = AsyncMock()

        asyncio.run(close_command(update, context))

        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        self.assertIn("can only be used in a group chat", reply_text)
        context.bot.leave_chat.assert_not_called()

        # Group still exists
        self.assertIsNotNone(GroupRepository(self.db_session).get_by_telegram_id(12345))

    def test_close_nonexistent_group(self):
        update = self.create_mock_message_update("/close", chat_id=99999)
        context = MagicMock()
        context.bot.leave_chat = AsyncMock()

        asyncio.run(close_command(update, context))

        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        self.assertIn("No active ledger or recorded transactions found", reply_text)
        context.bot.leave_chat.assert_not_called()

    def test_close_with_unsettled_debts_blocked(self):
        # Alice paid $30 split between Alice, Bob, Charlie (Bob owes $10, Charlie owes $10)
        splits = {self.alice.id: 1000, self.bob.id: 1000, self.charlie.id: 1000}
        crud.create_expense(
            self.db_session,
            group_id=self.group.id,
            payer_id=self.alice.id,
            amount=3000,
            description="Dinner",
            splits=splits,
        )
        self.db_session.commit()

        update = self.create_mock_message_update(
            "/close", chat_id=self.group.telegram_chat_id
        )
        context = MagicMock()
        context.bot.leave_chat = AsyncMock()

        asyncio.run(close_command(update, context))

        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        self.assertIn("Cannot close ledger: there are unsettled debts", reply_text)
        self.assertIn("Bob", reply_text)
        self.assertIn("Charlie", reply_text)
        context.bot.leave_chat.assert_not_called()

        # Verify group still exists with transactions intact
        group = GroupRepository(self.db_session).get_by_telegram_id(
            self.group.telegram_chat_id
        )
        self.assertIsNotNone(group)
        self.assertEqual(len(crud.get_group_expenses(self.db_session, group.id)), 1)

    def test_close_when_settled_deletes_group_and_leaves_chat(self):
        # Alice paid $20 split with Bob
        splits = {self.alice.id: 1000, self.bob.id: 1000}
        crud.create_expense(
            self.db_session,
            group_id=self.group.id,
            payer_id=self.alice.id,
            amount=2000,
            description="Lunch",
            splits=splits,
        )
        # Bob settles debt
        crud.create_payment(
            self.db_session,
            group_id=self.group.id,
            payer_id=self.bob.id,
            payee_id=self.alice.id,
            amount=1000,
        )
        # Register external member in this group
        external_user = crud.create_external_user(
            self.db_session,
            group=self.group,
            first_name="GuestEve",
        )
        self.db_session.commit()

        ext_user_id = external_user.id
        group_tg_id = self.group.telegram_chat_id

        update = self.create_mock_message_update("/close", chat_id=group_tg_id)
        context = MagicMock()
        context.bot.leave_chat = AsyncMock()

        asyncio.run(close_command(update, context))

        # Check farewell message was sent
        update.message.reply_text.assert_called_once()
        reply_text = update.message.reply_text.call_args[0][0]
        self.assertIn("All debts are settled! Ledger closed", reply_text)

        # Bot left chat
        context.bot.leave_chat.assert_called_once_with(chat_id=group_tg_id)

        # Database state: group and its records deleted
        group = GroupRepository(self.db_session).get_by_telegram_id(group_tg_id)
        self.assertIsNone(group)

        # External user specific to this group also cleaned up
        ext_in_db = self.db_session.query(User).filter_by(id=ext_user_id).first()
        self.assertIsNone(ext_in_db)

        # Regular users (Telegram accounts) remain intact
        self.assertIsNotNone(
            UserRepository(self.db_session).get_by_telegram_id(self.alice.telegram_id)
        )

    def test_recreate_group_after_close(self):
        # Close empty group
        update = self.create_mock_message_update(
            "/close", chat_id=self.group.telegram_chat_id
        )
        context = MagicMock()
        context.bot.leave_chat = AsyncMock()

        asyncio.run(close_command(update, context))

        # Group is gone
        self.assertIsNone(
            GroupRepository(self.db_session).get_by_telegram_id(
                self.group.telegram_chat_id
            )
        )

        # Re-adding bot / starting new ledger
        new_group = GroupRepository(self.db_session).get_or_create(
            self.group.telegram_chat_id, "New Ledger Group"
        )
        self.assertIsNotNone(new_group)
        self.assertEqual(len(crud.get_group_expenses(self.db_session, new_group.id)), 0)
        self.assertEqual(len(crud.get_group_payments(self.db_session, new_group.id)), 0)
