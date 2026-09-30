"""Unit tests for group lifecycle handler: bot entering a group."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from heathen_ledger.handlers.group import chat_member_update_handler
from heathen_ledger.repositories import GroupRepository
from telegram.constants import ChatMemberStatus, ChatType

from tests.base import BaseDatabaseTestCase


class TestGroupLifecycleHandlers(BaseDatabaseTestCase):
    """Test suite for group creation on bot join."""

    def test_bot_added_to_group_via_my_chat_member(self):
        update = MagicMock()
        chat_member_updated = MagicMock()

        chat = MagicMock()
        chat.id = -100999
        chat.title = "Vacation Group"
        chat.type = ChatType.GROUP

        chat_member_updated.chat = chat
        chat_member_updated.old_chat_member = MagicMock(status=ChatMemberStatus.LEFT)
        chat_member_updated.new_chat_member = MagicMock(status=ChatMemberStatus.MEMBER)
        update.my_chat_member = chat_member_updated

        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock()

        asyncio.run(chat_member_update_handler(update, context))

        group = GroupRepository(self.db_session).get_by_telegram_id(-100999)
        self.assertIsNotNone(group)
        self.assertEqual(group.title, "Vacation Group")

        context.bot.send_message.assert_called_once()
        call_kwargs = context.bot.send_message.call_args.kwargs
        self.assertEqual(call_kwargs["chat_id"], -100999)
        self.assertIn("Hello! I am Heathen Ledger", call_kwargs["text"])

    def test_bot_added_as_admin_via_my_chat_member(self):
        update = MagicMock()
        chat_member_updated = MagicMock()

        chat = MagicMock()
        chat.id = -100998
        chat.title = "Admin Supergroup"
        chat.type = ChatType.SUPERGROUP

        chat_member_updated.chat = chat
        chat_member_updated.old_chat_member = MagicMock(status=ChatMemberStatus.BANNED)
        chat_member_updated.new_chat_member = MagicMock(
            status=ChatMemberStatus.ADMINISTRATOR
        )
        update.my_chat_member = chat_member_updated

        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock()

        asyncio.run(chat_member_update_handler(update, context))

        group = GroupRepository(self.db_session).get_by_telegram_id(-100998)
        self.assertIsNotNone(group)
        self.assertEqual(group.title, "Admin Supergroup")
        context.bot.send_message.assert_called_once()

    def test_bot_status_change_while_already_member_does_not_resent_greeting(self):
        # Pre-create group
        GroupRepository(self.db_session).get_or_create(-100997, "Existing Group")

        update = MagicMock()
        chat_member_updated = MagicMock()

        chat = MagicMock()
        chat.id = -100997
        chat.title = "Existing Group"
        chat.type = ChatType.GROUP

        chat_member_updated.chat = chat
        chat_member_updated.old_chat_member = MagicMock(status=ChatMemberStatus.MEMBER)
        chat_member_updated.new_chat_member = MagicMock(
            status=ChatMemberStatus.ADMINISTRATOR
        )
        update.my_chat_member = chat_member_updated

        context = MagicMock()
        context.bot = AsyncMock()
        context.bot.send_message = AsyncMock()

        asyncio.run(chat_member_update_handler(update, context))

        context.bot.send_message.assert_not_called()
