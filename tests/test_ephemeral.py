"""Unit tests for ephemeral commands and persistent command variants."""

import unittest
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock
from telegram.constants import ChatType
from telegram.error import BadRequest

from heathen_ledger.handlers.common import (
    _get_ephemeral_message_id,
    is_persistent_command,
    send_response,
)
from heathen_ledger.handlers.settle import balances_command, settle_command
from heathen_ledger.handlers.history import history_command
from heathen_ledger.handlers.expense import pay_command, payback_command
from heathen_ledger.handlers.base import (
    register_command,
    members_command,
    help_command,
)
from tests.base import BaseDatabaseTestCase


class TestEphemeralHelpers(unittest.TestCase):
    def test_get_ephemeral_message_id_from_attribute(self):
        msg = MagicMock()
        msg.ephemeral_message_id = 12345
        self.assertEqual(_get_ephemeral_message_id(msg), 12345)

    def test_get_ephemeral_message_id_from_api_kwargs(self):
        msg = MagicMock(spec=[])
        msg.api_kwargs = MappingProxyType({"ephemeral_message_id": 67890})
        self.assertEqual(_get_ephemeral_message_id(msg), 67890)

    def test_get_ephemeral_message_id_from_reply(self):
        msg = MagicMock(spec=[])
        reply = MagicMock(spec=[])
        reply.api_kwargs = MappingProxyType({"ephemeral_message_id": 99999})
        msg.reply_to_message = reply
        self.assertEqual(_get_ephemeral_message_id(msg), 99999)

    def test_get_ephemeral_message_id_none(self):
        self.assertIsNone(_get_ephemeral_message_id(None))
        msg = MagicMock(spec=[])
        self.assertIsNone(_get_ephemeral_message_id(msg))

    def test_is_persistent_command(self):
        update = MagicMock()

        # /settle -> False
        update.effective_message.text = "/settle"
        self.assertFalse(is_persistent_command(update))

        # /settle_persistent -> True
        update.effective_message.text = "/settle_persistent"
        self.assertTrue(is_persistent_command(update))

        # /balances_persistent@MyBot -> True
        update.effective_message.text = "/balances_persistent@MyBot"
        self.assertTrue(is_persistent_command(update))

        # /pay_persistent 10 for Pizza -> True
        update.effective_message.text = "/pay_persistent 10 for Pizza"
        self.assertTrue(is_persistent_command(update))

        # /pay 10 for Pizza -> False
        update.effective_message.text = "/pay 10 for Pizza"
        self.assertFalse(is_persistent_command(update))


class TestSendResponse(unittest.IsolatedAsyncioTestCase):
    async def test_send_response_ephemeral_in_group(self):
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.GROUP
        update.effective_chat.id = -100123
        update.effective_user.id = 555
        update.effective_message.ephemeral_message_id = 4321
        update.effective_message.api_kwargs = None
        update.effective_message.text = "/settle"

        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await send_response(update, context, "Settlement summary")

        send_mock.assert_awaited_once()
        _, kwargs = send_mock.call_args
        self.assertEqual(kwargs.get("chat_id"), -100123)
        self.assertEqual(kwargs.get("text"), "Settlement summary")
        self.assertEqual(
            kwargs.get("api_kwargs"),
            {
                "ephemeral_message_parameters": {"receiver_user_id": 555},
                "reply_parameters": {"ephemeral_message_id": 4321},
            },
        )
        reply_markup = kwargs.get("reply_markup")
        self.assertIsNotNone(reply_markup)
        self.assertEqual(len(reply_markup.inline_keyboard), 1)
        row = reply_markup.inline_keyboard[0]
        self.assertEqual(len(row), 2)
        self.assertTrue(row[0].text.startswith("📢 Share to group"))
        self.assertTrue(row[0].callback_data.startswith("persist:"))
        self.assertEqual(row[1].text, "✕ Dismiss")
        self.assertTrue(
            row[1].callback_data == "dismiss"
            or row[1].callback_data.startswith("dismiss:")
        )

    async def test_send_response_error_only_has_dismiss(self):
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.GROUP
        update.effective_chat.id = -100123
        update.effective_user.id = 555
        update.effective_message.ephemeral_message_id = 4321
        update.effective_message.api_kwargs = None
        update.effective_message.text = "/pay invalid"

        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await send_response(update, context, "⚠️ Invalid amount")

        send_mock.assert_awaited_once()
        _, kwargs = send_mock.call_args
        reply_markup = kwargs.get("reply_markup")
        self.assertIsNotNone(reply_markup)
        row = reply_markup.inline_keyboard[0]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0].text, "✕ Dismiss")
        self.assertTrue(
            row[0].callback_data == "dismiss"
            or row[0].callback_data.startswith("dismiss:")
        )

    async def test_send_response_persistent_in_group(self):
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.SUPERGROUP
        update.effective_chat.id = -100456
        update.effective_user.id = 666
        update.effective_message.text = "/settle_persistent"

        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await send_response(update, context, "Public Settlement summary")

        send_mock.assert_awaited_once()
        _, kwargs = send_mock.call_args
        self.assertEqual(kwargs.get("chat_id"), -100456)
        self.assertEqual(kwargs.get("text"), "Public Settlement summary")
        self.assertIsNone(kwargs.get("api_kwargs"))

    async def test_send_response_fallback_on_bad_request(self):
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.GROUP
        update.effective_chat.id = -100123
        update.effective_user.id = 777
        update.effective_message.ephemeral_message_id = None
        update.effective_message.api_kwargs = None
        update.effective_message.text = "/balances"

        send_mock = AsyncMock(
            side_effect=[BadRequest("Admin rights required"), AsyncMock()]
        )
        context.bot.send_message = send_mock

        await send_response(update, context, "Balances info")

        self.assertEqual(send_mock.await_count, 2)
        fallback_call = send_mock.await_args_list[1]
        self.assertEqual(fallback_call.kwargs.get("chat_id"), -100123)
        self.assertIsNone(fallback_call.kwargs.get("api_kwargs"))

    async def test_send_response_in_private_chat(self):
        update = MagicMock()
        context = MagicMock()

        update.effective_chat.type = ChatType.PRIVATE
        update.effective_chat.id = 888
        update.effective_user.id = 888
        update.effective_message.text = "/balances"

        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await send_response(update, context, "Private balances")

        send_mock.assert_awaited_once()
        _, kwargs = send_mock.call_args
        self.assertEqual(kwargs.get("chat_id"), 888)
        self.assertIsNone(kwargs.get("api_kwargs"))


class TestPersistCallbackHandler(unittest.IsolatedAsyncioTestCase):
    async def test_persist_callback_handler_success(self):
        from heathen_ledger.handlers.common import (
            _PERSIST_PAYLOADS,
            persist_callback_handler,
        )
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton

        orig_keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Pay $10", callback_data="settle:1:2:10")]]
        )
        token = "test_token_123"
        _PERSIST_PAYLOADS[token] = {
            "chat_id": -100999,
            "user_id": 42,
            "text": "Original settlement text",
            "parse_mode": "Markdown",
            "reply_markup": orig_keyboard,
            "created_at": 100000.0,
        }

        update = MagicMock()
        context = MagicMock()
        update.callback_query.data = f"persist:{token}"
        update.callback_query.from_user.id = 42
        update.effective_user.id = 42
        update.callback_query.message.delete = AsyncMock()
        update.callback_query.answer = AsyncMock()
        context.bot.send_message = AsyncMock()

        await persist_callback_handler(update, context)

        # Verified public message sent with original markup (no Share/Dismiss buttons)
        context.bot.send_message.assert_awaited_once_with(
            chat_id=-100999,
            text="Original settlement text",
            parse_mode="Markdown",
            reply_markup=orig_keyboard,
        )
        # Ephemeral deleted
        update.callback_query.message.delete.assert_awaited_once()
        # Answered
        update.callback_query.answer.assert_awaited_once_with("Shared to group!")
        # Token removed from cache
        self.assertNotIn(token, _PERSIST_PAYLOADS)

    async def test_persist_callback_handler_expired_or_missing(self):
        from heathen_ledger.handlers.common import persist_callback_handler

        update = MagicMock()
        context = MagicMock()
        update.callback_query.data = "persist:nonexistent_token"
        update.callback_query.answer = AsyncMock()
        context.bot.send_message = AsyncMock()

        await persist_callback_handler(update, context)

        context.bot.send_message.assert_not_called()
        update.callback_query.answer.assert_awaited_once_with(
            "This message has expired or has already been shared.", show_alert=True
        )

    async def test_persist_callback_handler_other_user_prevented(self):
        from heathen_ledger.handlers.common import (
            _PERSIST_PAYLOADS,
            persist_callback_handler,
        )

        token = "token_for_user_42"
        _PERSIST_PAYLOADS[token] = {
            "chat_id": -100999,
            "user_id": 42,
            "text": "Private report",
            "parse_mode": "Markdown",
            "reply_markup": None,
            "created_at": 100000.0,
        }

        update = MagicMock()
        context = MagicMock()
        update.callback_query.data = f"persist:{token}"
        update.callback_query.from_user.id = 999  # Different user!
        update.effective_user.id = 999
        update.callback_query.answer = AsyncMock()
        context.bot.send_message = AsyncMock()

        await persist_callback_handler(update, context)

        context.bot.send_message.assert_not_called()
        update.callback_query.answer.assert_awaited_once_with(
            "Only the person who requested this message can share it.", show_alert=True
        )
        # Payload remains available for user 42
        self.assertIn(token, _PERSIST_PAYLOADS)

    async def test_persist_deletes_ephemeral_via_bot_post(self):
        from heathen_ledger.handlers.common import (
            _PERSIST_PAYLOADS,
            persist_callback_handler,
        )

        token = "token_post_test"
        _PERSIST_PAYLOADS[token] = {
            "chat_id": -100999,
            "user_id": 42,
            "text": "Shared content",
            "parse_mode": "Markdown",
            "reply_markup": None,
            "ephemeral_message_id": 9999,
            "created_at": 100000.0,
        }

        update = MagicMock()
        context = MagicMock()
        update.callback_query.data = f"persist:{token}"
        update.callback_query.from_user.id = 42
        update.effective_user.id = 42
        update.callback_query.message.delete = None  # not a mock method
        update.callback_query.answer = AsyncMock()
        context.bot.send_message = AsyncMock()
        context.bot._post = AsyncMock(return_value=True)

        await persist_callback_handler(update, context)

        context.bot._post.assert_awaited_once_with(
            "deleteEphemeralMessage",
            data={
                "chat_id": -100999,
                "receiver_user_id": 42,
                "ephemeral_message_id": 9999,
            },
        )
        update.callback_query.answer.assert_awaited_once_with("Shared to group!")


class TestDismissCallbackHandler(unittest.IsolatedAsyncioTestCase):
    async def test_dismiss_deletes_message(self):
        from heathen_ledger.handlers.common import dismiss_callback_handler

        update = MagicMock()
        context = MagicMock()
        update.callback_query.data = "dismiss"
        update.callback_query.message.delete = AsyncMock()
        update.callback_query.message.reply_to_message = None
        update.callback_query.answer = AsyncMock()

        await dismiss_callback_handler(update, context)

        update.callback_query.message.delete.assert_awaited_once()
        update.callback_query.answer.assert_awaited_once()

    async def test_dismiss_deletes_ephemeral_with_token(self):
        from heathen_ledger.handlers.common import (
            _PERSIST_PAYLOADS,
            dismiss_callback_handler,
        )

        token = "dismiss_tok_1"
        _PERSIST_PAYLOADS[token] = {
            "chat_id": -100888,
            "user_id": 77,
            "ephemeral_message_id": 8888,
            "created_at": 100000.0,
        }

        update = MagicMock()
        context = MagicMock()
        update.callback_query.data = f"dismiss:{token}"
        update.callback_query.from_user.id = 77
        update.callback_query.message.delete = None
        update.callback_query.message.reply_to_message = None
        update.callback_query.answer = AsyncMock()
        context.bot._post = AsyncMock(return_value=True)

        await dismiss_callback_handler(update, context)

        context.bot._post.assert_awaited_once_with(
            "deleteEphemeralMessage",
            data={
                "chat_id": -100888,
                "receiver_user_id": 77,
                "ephemeral_message_id": 8888,
            },
        )
        update.callback_query.answer.assert_awaited_once()
        self.assertNotIn(token, _PERSIST_PAYLOADS)

    async def test_dismiss_deletes_ephemeral_from_query_message(self):
        from types import MappingProxyType
        from heathen_ledger.handlers.common import dismiss_callback_handler

        update = MagicMock()
        context = MagicMock()
        update.callback_query.data = "dismiss"
        update.callback_query.from_user.id = 55
        update.callback_query.message.chat.id = -100555
        update.callback_query.message.api_kwargs = MappingProxyType(
            {"ephemeral_message_id": 5555}
        )
        update.callback_query.message.delete = None
        update.callback_query.message.reply_to_message = None
        update.callback_query.answer = AsyncMock()
        context.bot._post = AsyncMock(return_value=True)

        await dismiss_callback_handler(update, context)

        context.bot._post.assert_awaited_once_with(
            "deleteEphemeralMessage",
            data={
                "chat_id": -100555,
                "receiver_user_id": 55,
                "ephemeral_message_id": 5555,
            },
        )

    async def test_dismiss_fallback_to_edit_on_bad_request(self):
        from types import MappingProxyType
        from heathen_ledger.handlers.common import dismiss_callback_handler

        update = MagicMock()
        context = MagicMock()
        update.callback_query.data = "dismiss"
        update.callback_query.from_user.id = 55
        update.callback_query.message.chat.id = -100555
        update.callback_query.message.api_kwargs = MappingProxyType(
            {"ephemeral_message_id": 5555}
        )
        update.callback_query.message.reply_to_message = None
        update.callback_query.answer = AsyncMock()
        # First call (deleteEphemeralMessage) raises BadRequest, second call (editEphemeralMessageText) succeeds
        context.bot._post = AsyncMock(
            side_effect=[BadRequest("Message to delete not found"), True]
        )

        await dismiss_callback_handler(update, context)

        self.assertEqual(context.bot._post.await_count, 2)
        edit_call = context.bot._post.await_args_list[1]
        self.assertEqual(edit_call.args[0], "editEphemeralMessageText")
        self.assertEqual(
            edit_call.kwargs.get("data", {}).get("text"), "🗑️ Message dismissed."
        )
        update.callback_query.answer.assert_awaited_once()


class TestCommandsEphemeralAndPersistent(BaseDatabaseTestCase):
    def test_balances_ephemeral_vs_persistent(self):
        # 1. Ephemeral invocation
        update_eph = self.create_mock_message_update("/balances")
        update_eph.effective_chat.type = ChatType.GROUP
        update_eph.effective_message.ephemeral_message_id = 111
        context_eph = MagicMock()
        send_eph = AsyncMock()
        context_eph.bot.send_message = send_eph

        import asyncio

        asyncio.run(balances_command(update_eph, context_eph))
        send_eph.assert_awaited_once()
        _, kwargs = send_eph.call_args
        self.assertIn("ephemeral_message_parameters", kwargs.get("api_kwargs", {}))

        # 2. Persistent invocation
        update_pers = self.create_mock_message_update("/balances_persistent")
        update_pers.effective_chat.type = ChatType.GROUP
        context_pers = MagicMock()
        send_pers = AsyncMock()
        context_pers.bot.send_message = send_pers

        asyncio.run(balances_command(update_pers, context_pers))
        send_pers.assert_awaited_once()
        _, kwargs = send_pers.call_args
        self.assertIsNone(kwargs.get("api_kwargs"))

    def test_settle_ephemeral_vs_persistent(self):
        # 1. Ephemeral invocation
        update_eph = self.create_mock_message_update("/settle")
        update_eph.effective_chat.type = ChatType.GROUP
        update_eph.effective_message.ephemeral_message_id = 222
        context_eph = MagicMock()
        send_eph = AsyncMock()
        context_eph.bot.send_message = send_eph

        import asyncio

        asyncio.run(settle_command(update_eph, context_eph))
        send_eph.assert_awaited_once()
        _, kwargs = send_eph.call_args
        self.assertIn("ephemeral_message_parameters", kwargs.get("api_kwargs", {}))

        # 2. Persistent invocation
        update_pers = self.create_mock_message_update("/settle_persistent")
        update_pers.effective_chat.type = ChatType.GROUP
        context_pers = MagicMock()
        send_pers = AsyncMock()
        context_pers.bot.send_message = send_pers

        asyncio.run(settle_command(update_pers, context_pers))
        send_pers.assert_awaited_once()
        _, kwargs = send_pers.call_args
        self.assertIsNone(kwargs.get("api_kwargs"))

    def test_history_ephemeral_vs_persistent(self):
        update_eph = self.create_mock_message_update("/history")
        update_eph.effective_chat.type = ChatType.GROUP
        update_eph.effective_message.ephemeral_message_id = 333
        context_eph = MagicMock()
        send_eph = AsyncMock()
        context_eph.bot.send_message = send_eph

        import asyncio

        asyncio.run(history_command(update_eph, context_eph))
        send_eph.assert_awaited_once()
        self.assertIn(
            "ephemeral_message_parameters",
            send_eph.call_args.kwargs.get("api_kwargs", {}),
        )

        update_pers = self.create_mock_message_update("/history_persistent")
        update_pers.effective_chat.type = ChatType.GROUP
        context_pers = MagicMock()
        send_pers = AsyncMock()
        context_pers.bot.send_message = send_pers

        asyncio.run(history_command(update_pers, context_pers))
        send_pers.assert_awaited_once()
        self.assertIsNone(send_pers.call_args.kwargs.get("api_kwargs"))

    def test_pay_ephemeral_vs_persistent(self):
        update_eph = self.create_mock_message_update("/pay 20 for Snacks")
        update_eph.effective_chat.type = ChatType.GROUP
        update_eph.effective_message.ephemeral_message_id = 444
        context_eph = MagicMock()
        send_eph = AsyncMock()
        context_eph.bot.send_message = send_eph

        import asyncio

        asyncio.run(pay_command(update_eph, context_eph))
        send_eph.assert_awaited_once()
        self.assertIn(
            "ephemeral_message_parameters",
            send_eph.call_args.kwargs.get("api_kwargs", {}),
        )

        update_pers = self.create_mock_message_update("/pay_persistent 20 for Drinks")
        update_pers.effective_chat.type = ChatType.GROUP
        context_pers = MagicMock()
        send_pers = AsyncMock()
        context_pers.bot.send_message = send_pers

        asyncio.run(pay_command(update_pers, context_pers))
        send_pers.assert_awaited_once()
        self.assertIsNone(send_pers.call_args.kwargs.get("api_kwargs"))

    def test_payback_ephemeral_vs_persistent(self):
        update_eph = self.create_mock_message_update("/payback @bob 10")
        update_eph.effective_chat.type = ChatType.GROUP
        update_eph.effective_message.ephemeral_message_id = 555
        context_eph = MagicMock()
        send_eph = AsyncMock()
        context_eph.bot.send_message = send_eph

        import asyncio

        asyncio.run(payback_command(update_eph, context_eph))
        send_eph.assert_awaited_once()
        self.assertIn(
            "ephemeral_message_parameters",
            send_eph.call_args.kwargs.get("api_kwargs", {}),
        )

        update_pers = self.create_mock_message_update("/payback_persistent @bob 10")
        update_pers.effective_chat.type = ChatType.GROUP
        context_pers = MagicMock()
        send_pers = AsyncMock()
        context_pers.bot.send_message = send_pers

        asyncio.run(payback_command(update_pers, context_pers))
        send_pers.assert_awaited_once()
        self.assertIsNone(send_pers.call_args.kwargs.get("api_kwargs"))

    def test_register_ephemeral_vs_persistent(self):
        # 1. Ephemeral /register with no args
        update_eph = self.create_mock_message_update("/register")
        update_eph.effective_chat.type = ChatType.GROUP
        update_eph.effective_message.ephemeral_message_id = 666
        context_eph = MagicMock()
        send_eph = AsyncMock()
        context_eph.bot.send_message = send_eph

        import asyncio

        asyncio.run(register_command(update_eph, context_eph))
        send_eph.assert_awaited_once()
        self.assertIn(
            "ephemeral_message_parameters",
            send_eph.call_args.kwargs.get("api_kwargs", {}),
        )

        # 2. Persistent /register_persistent with no args (public button for members)
        update_pers = self.create_mock_message_update("/register_persistent")
        update_pers.effective_chat.type = ChatType.GROUP
        context_pers = MagicMock()
        send_pers = AsyncMock()
        context_pers.bot.send_message = send_pers

        asyncio.run(register_command(update_pers, context_pers))
        send_pers.assert_awaited_once()
        self.assertIsNone(send_pers.call_args.kwargs.get("api_kwargs"))

    def test_members_ephemeral_vs_persistent(self):
        update_eph = self.create_mock_message_update("/members")
        update_eph.effective_chat.type = ChatType.GROUP
        update_eph.effective_message.ephemeral_message_id = 777
        context_eph = MagicMock()
        send_eph = AsyncMock()
        context_eph.bot.send_message = send_eph

        import asyncio

        asyncio.run(members_command(update_eph, context_eph))
        send_eph.assert_awaited_once()
        self.assertIn(
            "ephemeral_message_parameters",
            send_eph.call_args.kwargs.get("api_kwargs", {}),
        )

        update_pers = self.create_mock_message_update("/members_persistent")
        update_pers.effective_chat.type = ChatType.GROUP
        context_pers = MagicMock()
        send_pers = AsyncMock()
        context_pers.bot.send_message = send_pers

        asyncio.run(members_command(update_pers, context_pers))
        send_pers.assert_awaited_once()
        self.assertIsNone(send_pers.call_args.kwargs.get("api_kwargs"))


class TestCommandRegistration(unittest.IsolatedAsyncioTestCase):
    async def test_post_init_sets_only_single_commands(self):
        from heathen_ledger.bot import post_init
        from telegram import BotCommandScopeAllGroupChats

        app_mock = MagicMock()
        app_mock.bot.set_my_commands = AsyncMock()

        await post_init(app_mock)

        # At least two calls: default scope and group scope
        self.assertGreaterEqual(app_mock.bot.set_my_commands.await_count, 2)

        # 1. Default commands should only contain single commands (no _persistent duplicates)
        default_commands = app_mock.bot.set_my_commands.call_args_list[0].args[0]
        cmd_names = [c.command for c in default_commands]
        expected_commands = [
            "pay",
            "balances",
            "settle",
            "payback",
            "history",
            "register",
            "members",
            "voice",
            "help",
        ]
        self.assertEqual(cmd_names, expected_commands)
        for cmd in cmd_names:
            self.assertFalse(
                cmd.endswith("_persistent"),
                f"Command '{cmd}' should not have _persistent variant in autocomplete list",
            )

        # 2. Group scope commands should be the exact same single commands with is_ephemeral=True
        group_call = next(
            call
            for call in app_mock.bot.set_my_commands.call_args_list
            if isinstance(call.kwargs.get("scope"), BotCommandScopeAllGroupChats)
        )
        group_commands = group_call.args[0]
        group_cmd_names = [c.command for c in group_commands]
        self.assertEqual(group_cmd_names, expected_commands)
        for cmd in group_commands:
            self.assertTrue(
                cmd.api_kwargs.get("is_ephemeral"),
                f"Command '{cmd.command}' should be ephemeral in group scope",
            )

    async def test_register_handlers_includes_persist_and_dismiss_callbacks(self):
        from heathen_ledger.handlers import register_handlers
        from telegram.ext import CallbackQueryHandler

        app_mock = MagicMock()
        register_handlers(app_mock)

        patterns = []
        for call in app_mock.add_handler.call_args_list:
            handler = call[0][0]
            if isinstance(handler, CallbackQueryHandler):
                patterns.append(
                    getattr(handler.pattern, "pattern", str(handler.pattern))
                )

        self.assertIn("^persist:", patterns)
        self.assertIn("^dismiss(:.*)?$", patterns)

    async def test_help_command_explains_ephemeral_and_buttons(self):
        update = MagicMock()
        context = MagicMock()
        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await help_command(update, context)

        send_mock.assert_awaited_once()
        help_text = (
            send_mock.call_args.kwargs.get("text") or send_mock.call_args.args[0]
        )
        self.assertIn("Ephemeral Responses & Sharing", help_text)
        self.assertIn("Share to group", help_text)
        self.assertIn("Dismiss", help_text)
        self.assertNotIn("/settle_persistent", help_text)


if __name__ == "__main__":
    unittest.main()
