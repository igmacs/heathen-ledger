"""Unit tests for TelegramRichClient adapter for Rich Messages."""

import asyncio
import unittest
from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from heathen_ledger.telegram.rich_client import TelegramRichClient


class TestTelegramRichClient(unittest.TestCase):
    def test_build_rich_message_payload(self):
        html = "<p>Test <b>content</b></p>"
        payload = TelegramRichClient.build_rich_message_payload(html)
        self.assertEqual(payload, {"html": html})

    def test_send_rich_message_future_native(self):
        bot = MagicMock(spec=["send_rich_message"])
        bot.send_rich_message = AsyncMock(return_value="sent_message")

        html = "<p>Hello</p>"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("OK", callback_data="ok")]]
        )

        res = asyncio.run(
            TelegramRichClient.send_rich_message(
                bot,
                chat_id=123,
                rich_html=html,
                reply_markup=keyboard,
                ephemeral_message_parameters={"receiver_user_id": 456},
                disable_notification=True,
            )
        )
        self.assertEqual(res, "sent_message")
        bot.send_rich_message.assert_awaited_once_with(
            chat_id=123,
            rich_message={"html": html},
            reply_markup=keyboard,
            ephemeral_message_parameters={"receiver_user_id": 456},
            disable_notification=True,
        )

    def test_send_rich_message_via_post(self):
        bot = MagicMock(spec=["_post"])
        bot._post = AsyncMock(return_value={"message_id": 99})

        html = "<p>Hello from rich</p>"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Action", callback_data="act")]]
        )

        res = asyncio.run(
            TelegramRichClient.send_rich_message(
                bot,
                chat_id=123,
                rich_html=html,
                reply_markup=keyboard,
                ephemeral_message_parameters={"receiver_user_id": 456},
            )
        )
        self.assertEqual(res, {"message_id": 99})
        bot._post.assert_awaited_once_with(
            "sendRichMessage",
            data={
                "chat_id": 123,
                "rich_message": {"html": html},
                "ephemeral_message_parameters": {"receiver_user_id": 456},
                "reply_markup": keyboard.to_dict(),
            },
        )

    def test_send_rich_message_with_reply_parameters_via_post(self):
        bot = MagicMock(spec=["_post"])
        bot._post = AsyncMock(return_value={"message_id": 100})

        html = "<p>With reply params</p>"
        reply_params = {"ephemeral_message_id": 4321}

        res = asyncio.run(
            TelegramRichClient.send_rich_message(
                bot,
                chat_id=123,
                rich_html=html,
                ephemeral_message_parameters={"receiver_user_id": 456},
                reply_parameters=reply_params,
            )
        )
        self.assertEqual(res, {"message_id": 100})
        bot._post.assert_awaited_once_with(
            "sendRichMessage",
            data={
                "chat_id": 123,
                "rich_message": {"html": html},
                "ephemeral_message_parameters": {"receiver_user_id": 456},
                "reply_parameters": reply_params,
            },
        )

    def test_send_rich_message_mock_send_message_fallback(self):
        bot = MagicMock(spec=["send_message"])
        bot.send_message = AsyncMock(return_value="fallback_msg")

        html = "<p>Rich content</p>"
        res = asyncio.run(
            TelegramRichClient.send_rich_message(
                bot,
                chat_id=123,
                rich_html=html,
                fallback_text="Fallback text",
                parse_mode="Markdown",
            )
        )
        self.assertEqual(res, "fallback_msg")
        bot.send_message.assert_awaited_once_with(
            chat_id=123,
            text="Fallback text",
            parse_mode="Markdown",
            reply_markup=None,
            api_kwargs={"rich_message": {"html": html}},
        )

    def test_edit_rich_message_text_via_post(self):
        bot = MagicMock(spec=["_post"])
        bot._post = AsyncMock(return_value=True)

        html = "<p>Updated rich content</p>"
        res = asyncio.run(
            TelegramRichClient.edit_rich_message_text(
                bot,
                chat_id=123,
                message_id=456,
                rich_html=html,
            )
        )
        self.assertTrue(res)
        bot._post.assert_awaited_once_with(
            "editMessageText",
            data={
                "chat_id": 123,
                "message_id": 456,
                "rich_message": {"html": html},
            },
        )

    def test_edit_ephemeral_rich_message_text_via_post(self):
        bot = MagicMock(spec=["_post"])
        bot._post = AsyncMock(return_value=True)

        html = "<p>Updated ephemeral rich</p>"
        res = asyncio.run(
            TelegramRichClient.edit_ephemeral_rich_message_text(
                bot,
                chat_id=123,
                receiver_user_id=789,
                ephemeral_message_id=555,
                rich_html=html,
            )
        )
        self.assertTrue(res)
        bot._post.assert_awaited_once_with(
            "editEphemeralMessageText",
            data={
                "chat_id": 123,
                "receiver_user_id": 789,
                "ephemeral_message_id": 555,
                "rich_message": {"html": html},
            },
        )

    def test_edit_rich_message_or_ephemeral_mock_query(self):
        query = MagicMock()
        query.edit_message_text = AsyncMock()

        html = "<p>Query edit</p>"
        res = asyncio.run(
            TelegramRichClient.edit_rich_message_or_ephemeral(
                query=query,
                rich_html=html,
                fallback_text="Fallback",
            )
        )
        self.assertTrue(res)
        query.edit_message_text.assert_awaited_once_with(
            text="Fallback",
            reply_markup=None,
            api_kwargs={"rich_message": {"html": html}},
        )

    def test_edit_rich_message_or_ephemeral_detects_ephemeral(self):
        bot = MagicMock(spec=["_post"])
        bot._post = AsyncMock(return_value=True)

        query = MagicMock(spec=["message", "from_user"])
        query.from_user.id = 888
        query.message.chat.id = 999
        query.message.message_id = 0
        query.message.api_kwargs = MappingProxyType({"ephemeral_message_id": 777})

        html = "<p>Updated ephemeral</p>"
        res = asyncio.run(
            TelegramRichClient.edit_rich_message_or_ephemeral(
                query=query,
                bot=bot,
                rich_html=html,
            )
        )
        self.assertTrue(res)
        bot._post.assert_awaited_once_with(
            "editEphemeralMessageText",
            data={
                "chat_id": 999,
                "receiver_user_id": 888,
                "ephemeral_message_id": 777,
                "rich_message": {"html": html},
            },
        )


if __name__ == "__main__":
    unittest.main()
