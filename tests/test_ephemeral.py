"""Unit tests for the ephemeral message command handler."""

import unittest
from unittest.mock import AsyncMock, MagicMock
from telegram.constants import ChatType
from telegram.error import BadRequest

from heathen_ledger.handlers.ephemeral import ephemeral_command


class TestEphemeralCommandHandler(unittest.IsolatedAsyncioTestCase):
    async def test_ephemeral_in_group(self):
        """Test sending an ephemeral message in a group chat."""
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.GROUP
        update.effective_chat.id = -100123456
        update.effective_user.id = 999
        update.effective_user.first_name = "Alice"
        update.effective_user.username = "alice"

        reply_mock = AsyncMock()
        update.effective_message.reply_text = reply_mock

        await ephemeral_command(update, context)

        reply_mock.assert_awaited_once()
        args, kwargs = reply_mock.call_args
        self.assertIn("Ephemeral Message Proof of Concept", args[0])
        self.assertIn("Alice", args[0])
        self.assertIn("999", args[0])
        self.assertEqual(kwargs.get("parse_mode"), "Markdown")
        self.assertEqual(
            kwargs.get("api_kwargs"),
            {"ephemeral_message_parameters": {"receiver_user_id": 999}},
        )

    async def test_ephemeral_in_supergroup(self):
        """Test sending an ephemeral message in a supergroup chat."""
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.SUPERGROUP
        update.effective_chat.id = -100987654
        update.effective_user.id = 888
        update.effective_user.first_name = "Bob"
        update.effective_user.username = "bob"

        reply_mock = AsyncMock()
        update.effective_message.reply_text = reply_mock

        await ephemeral_command(update, context)

        reply_mock.assert_awaited_once()
        args, kwargs = reply_mock.call_args
        self.assertIn("Bob", args[0])
        self.assertEqual(
            kwargs.get("api_kwargs"),
            {"ephemeral_message_parameters": {"receiver_user_id": 888}},
        )

    async def test_ephemeral_group_bad_request_fallback(self):
        """Test fallback error message when Telegram rejects ephemeral parameters in group."""
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.GROUP
        update.effective_chat.id = -100123456
        update.effective_user.id = 777
        update.effective_user.first_name = "Charlie"
        update.effective_user.username = "charlie"

        reply_mock = AsyncMock(
            side_effect=[BadRequest("Ephemeral not supported"), AsyncMock()]
        )
        update.effective_message.reply_text = reply_mock

        await ephemeral_command(update, context)

        self.assertEqual(reply_mock.await_count, 2)
        fallback_call = reply_mock.await_args_list[1]
        self.assertIn("Ephemeral message error", fallback_call[0][0])
        self.assertIn("Ephemeral not supported", fallback_call[0][0])

    async def test_ephemeral_in_private_chat(self):
        """Test ephemeral command behavior in a 1-on-1 private chat."""
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.PRIVATE
        update.effective_chat.id = 666
        update.effective_user.id = 666
        update.effective_user.first_name = "Dave"
        update.effective_user.username = "dave"

        reply_mock = AsyncMock()
        update.effective_message.reply_text = reply_mock

        await ephemeral_command(update, context)

        reply_mock.assert_awaited_once()
        args, kwargs = reply_mock.call_args
        self.assertIn("In a private 1-on-1 chat", args[0])
        self.assertIn("Dave", args[0])
        self.assertEqual(
            kwargs.get("api_kwargs"),
            {"ephemeral_message_parameters": {"receiver_user_id": 666}},
        )

    async def test_ephemeral_in_private_chat_bad_request_fallback(self):
        """Test that private chat gracefully falls back if Telegram rejects api_kwargs."""
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.PRIVATE
        update.effective_chat.id = 555
        update.effective_user.id = 555
        update.effective_user.first_name = "Eve"
        update.effective_user.username = "eve"

        reply_mock = AsyncMock(
            side_effect=[BadRequest("Not allowed in private chat"), AsyncMock()]
        )
        update.effective_message.reply_text = reply_mock

        await ephemeral_command(update, context)

        self.assertEqual(reply_mock.await_count, 2)
        fallback_call = reply_mock.await_args_list[1]
        self.assertIn("In a private 1-on-1 chat", fallback_call[0][0])
        self.assertIsNone(fallback_call[1].get("api_kwargs"))

    async def test_early_return_when_missing_message_or_user(self):
        """Test that missing message or user returns cleanly without error."""
        context = MagicMock()

        # Missing effective_message
        update1 = MagicMock()
        update1.effective_message = None
        update1.effective_user = MagicMock()
        await ephemeral_command(update1, context)

        # Missing effective_user
        update2 = MagicMock()
        update2.effective_message = MagicMock()
        update2.effective_user = None
        await ephemeral_command(update2, context)
        update2.effective_message.reply_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
