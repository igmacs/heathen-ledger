"""Unit tests for ephemeral commands and persistent command variants."""

import unittest
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import CommandHandler

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
    async def test_post_init_sets_all_group_commands_as_ephemeral(self):
        from heathen_ledger.bot import post_init
        from telegram import BotCommandScopeAllGroupChats

        app_mock = MagicMock()
        app_mock.bot.set_my_commands = AsyncMock()

        await post_init(app_mock)

        # At least two calls: default scope and group scope
        self.assertGreaterEqual(app_mock.bot.set_my_commands.await_count, 2)
        group_call = next(
            call
            for call in app_mock.bot.set_my_commands.call_args_list
            if isinstance(call.kwargs.get("scope"), BotCommandScopeAllGroupChats)
        )
        group_commands = group_call.args[0]
        for cmd in group_commands:
            self.assertTrue(
                cmd.api_kwargs.get("is_ephemeral"),
                f"Command '{cmd.command}' should be ephemeral in group scope",
            )

        cmd_names = [c.command for c in group_commands]
        self.assertIn("settle", cmd_names)
        self.assertIn("settle_persistent", cmd_names)
        self.assertIn("balances", cmd_names)
        self.assertIn("balances_persistent", cmd_names)
        self.assertIn("history", cmd_names)
        self.assertIn("history_persistent", cmd_names)
        self.assertIn("pay", cmd_names)
        self.assertIn("pay_persistent", cmd_names)

        # Ensure removed PoC commands are not present
        self.assertNotIn("ephemeral", cmd_names)
        self.assertNotIn("whisper", cmd_names)
        self.assertNotIn("test_ephemeral", cmd_names)

    async def test_register_handlers_includes_persistent_variants(self):
        from heathen_ledger.handlers import register_handlers

        app_mock = MagicMock()
        register_handlers(app_mock)

        registered_commands = []
        for call in app_mock.add_handler.call_args_list:
            handler = call[0][0]
            if isinstance(handler, CommandHandler):
                registered_commands.extend(list(handler.commands))

        self.assertIn("settle", registered_commands)
        self.assertIn("settle_persistent", registered_commands)
        self.assertIn("balances", registered_commands)
        self.assertIn("balances_persistent", registered_commands)
        self.assertIn("history", registered_commands)
        self.assertIn("history_persistent", registered_commands)
        self.assertIn("pay", registered_commands)
        self.assertIn("pay_persistent", registered_commands)
        self.assertIn("payback", registered_commands)
        self.assertIn("payback_persistent", registered_commands)
        self.assertIn("register", registered_commands)
        self.assertIn("register_persistent", registered_commands)
        self.assertIn("members", registered_commands)
        self.assertIn("members_persistent", registered_commands)

        # Removed PoC commands
        self.assertNotIn("ephemeral", registered_commands)
        self.assertNotIn("whisper", registered_commands)
        self.assertNotIn("test_ephemeral", registered_commands)

    async def test_help_command_explains_ephemeral_and_persistent(self):
        update = MagicMock()
        context = MagicMock()
        send_mock = AsyncMock()
        context.bot.send_message = send_mock

        await help_command(update, context)

        send_mock.assert_awaited_once()
        help_text = (
            send_mock.call_args.kwargs.get("text") or send_mock.call_args.args[0]
        )
        self.assertIn("Ephemeral & Persistent Commands", help_text)
        self.assertIn("/settle_persistent", help_text)


if __name__ == "__main__":
    unittest.main()
