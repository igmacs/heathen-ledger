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
        update.effective_message.ephemeral_message_id = None
        update.effective_message.api_kwargs = None

        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await ephemeral_command(update, context)

        send_mock.assert_awaited_once()
        _, kwargs = send_mock.call_args
        self.assertEqual(kwargs.get("chat_id"), -100123456)
        self.assertIn("Ephemeral Command Test", kwargs.get("text"))
        self.assertIn("Alice", kwargs.get("text"))
        self.assertIn("999", kwargs.get("text"))
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
        update.effective_message.ephemeral_message_id = None
        update.effective_message.api_kwargs = None

        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await ephemeral_command(update, context)

        send_mock.assert_awaited_once()
        _, kwargs = send_mock.call_args
        self.assertIn("Bob", kwargs.get("text"))
        self.assertEqual(
            kwargs.get("api_kwargs"),
            {"ephemeral_message_parameters": {"receiver_user_id": 888}},
        )

    async def test_ephemeral_with_incoming_ephemeral_message_id(self):
        """Test sending an ephemeral message when incoming command carries ephemeral_message_id."""
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.GROUP
        update.effective_chat.id = -100123456
        update.effective_user.id = 555
        update.effective_user.first_name = "Frank"
        update.effective_user.username = "frank"
        update.effective_message.ephemeral_message_id = 1234
        update.effective_message.api_kwargs = None

        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await ephemeral_command(update, context)

        send_mock.assert_awaited_once()
        _, kwargs = send_mock.call_args
        self.assertIn("Two-way privacy active", kwargs.get("text"))
        self.assertEqual(
            kwargs.get("api_kwargs"),
            {
                "ephemeral_message_parameters": {"receiver_user_id": 555},
                "reply_parameters": {"ephemeral_message_id": 1234},
            },
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
        update.effective_message.ephemeral_message_id = None
        update.effective_message.api_kwargs = None

        context.bot.send_message = AsyncMock(
            side_effect=BadRequest("Ephemeral not supported")
        )
        reply_mock = AsyncMock()
        update.effective_message.reply_text = reply_mock

        await ephemeral_command(update, context)

        reply_mock.assert_awaited_once()
        fallback_call = reply_mock.call_args
        self.assertIn("Ephemeral Message Error", fallback_call[0][0])
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

        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await ephemeral_command(update, context)

        send_mock.assert_awaited_once()
        _, kwargs = send_mock.call_args
        self.assertEqual(kwargs.get("chat_id"), 666)
        self.assertIn("In a private 1-on-1 chat", kwargs.get("text"))
        self.assertIn("Dave", kwargs.get("text"))
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

        context.bot.send_message = AsyncMock(
            side_effect=BadRequest("Not allowed in private chat")
        )
        reply_mock = AsyncMock()
        update.effective_message.reply_text = reply_mock

        await ephemeral_command(update, context)

        reply_mock.assert_awaited_once()
        fallback_call = reply_mock.call_args
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

    async def test_register_handlers_includes_ephemeral(self):
        """Test that register_handlers adds the CommandHandler for ephemeral and test_ephemeral."""
        from heathen_ledger.handlers import register_handlers
        from telegram.ext import CommandHandler

        app_mock = MagicMock()
        register_handlers(app_mock)

        # Collect registered command names
        registered_commands = []
        for call in app_mock.add_handler.call_args_list:
            handler = call[0][0]
            if isinstance(handler, CommandHandler):
                registered_commands.extend(list(handler.commands))

        self.assertIn("ephemeral", registered_commands)
        self.assertIn("whisper", registered_commands)
        self.assertIn("test_ephemeral", registered_commands)

    async def test_post_init_sets_ephemeral_bot_command(self):
        """Test that post_init registers ephemeral and whisper commands with is_ephemeral=True."""
        from heathen_ledger.bot import post_init

        app_mock = MagicMock()
        app_mock.bot.set_my_commands = AsyncMock()

        await post_init(app_mock)

        self.assertGreaterEqual(app_mock.bot.set_my_commands.await_count, 1)
        commands = app_mock.bot.set_my_commands.call_args_list[0][0][0]
        ephemeral_cmd = next((c for c in commands if c.command == "ephemeral"), None)
        whisper_cmd = next((c for c in commands if c.command == "whisper"), None)
        self.assertIsNotNone(ephemeral_cmd)
        self.assertTrue(ephemeral_cmd.api_kwargs.get("is_ephemeral"))
        self.assertIsNotNone(whisper_cmd)
        self.assertTrue(whisper_cmd.api_kwargs.get("is_ephemeral"))

    async def test_help_command_includes_ephemeral(self):
        """Test that /help lists the ephemeral command."""
        from heathen_ledger.handlers.base import help_command

        update = MagicMock()
        context = MagicMock()
        update.message.reply_text = AsyncMock()

        await help_command(update, context)

        update.message.reply_text.assert_awaited_once()
        reply_text = update.message.reply_text.call_args[0][0]
        self.assertIn("/ephemeral", reply_text)

    async def test_ephemeral_callback_handler_success(self):
        """Test ephemeral callback handler sends ephemeral message using callback_query_id."""
        from heathen_ledger.handlers.ephemeral import ephemeral_callback_handler

        update = MagicMock()
        context = MagicMock()

        update.callback_query.id = "cq_12345"
        update.callback_query.from_user.id = 444
        update.callback_query.from_user.first_name = "Grace"
        update.callback_query.from_user.username = "grace"
        update.callback_query.answer = AsyncMock()

        update.effective_chat.id = -100999
        context.bot.send_message = AsyncMock()

        await ephemeral_callback_handler(update, context)

        context.bot.send_message.assert_awaited_once()
        args, kwargs = context.bot.send_message.call_args
        self.assertEqual(kwargs.get("chat_id"), -100999)
        self.assertIn("Grace", kwargs.get("text"))
        self.assertEqual(
            kwargs.get("api_kwargs"),
            {
                "ephemeral_message_parameters": {
                    "receiver_user_id": 444,
                    "callback_query_id": "cq_12345",
                }
            },
        )
        update.callback_query.answer.assert_awaited_once_with()

    async def test_ephemeral_callback_handler_bad_request(self):
        """Test ephemeral callback handler handles BadRequest gracefully."""
        from heathen_ledger.handlers.ephemeral import ephemeral_callback_handler

        update = MagicMock()
        context = MagicMock()

        update.callback_query.id = "cq_12345"
        update.callback_query.from_user.id = 444
        update.callback_query.from_user.first_name = "Grace"
        update.callback_query.from_user.username = "grace"
        update.callback_query.answer = AsyncMock()

        update.effective_chat.id = -100999
        context.bot.send_message = AsyncMock(side_effect=BadRequest("Expired query"))

        await ephemeral_callback_handler(update, context)

        update.callback_query.answer.assert_awaited_once()
        _, kwargs = update.callback_query.answer.call_args
        self.assertTrue(kwargs.get("show_alert"))

    async def test_register_handlers_includes_ephemeral_callback(self):
        """Test that register_handlers registers the ephemeral callback query handler."""
        from heathen_ledger.handlers import register_handlers
        from telegram.ext import CallbackQueryHandler

        app_mock = MagicMock()
        register_handlers(app_mock)

        callback_patterns = []
        for call in app_mock.add_handler.call_args_list:
            handler = call[0][0]
            if isinstance(handler, CallbackQueryHandler) and hasattr(
                handler, "pattern"
            ):
                callback_patterns.append(str(handler.pattern.pattern))

        self.assertTrue(any("ephemeral_cb" in p for p in callback_patterns))


if __name__ == "__main__":
    unittest.main()
