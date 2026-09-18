import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from telegram.constants import ChatType

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.handlers.receipt import (
    ticket_command_handler,
    ticket_photo_handler,
    ticket_mention_handler,
    is_image_media,
)
from heathen_ledger.handlers import reply_mention_dispatcher
from heathen_ledger.receipt import Receipt, ReceiptItem


class TestReceiptHandler(unittest.IsolatedAsyncioTestCase):
    def test_is_image_media(self):
        msg_none = None
        self.assertFalse(is_image_media(msg_none))

        msg_photo = MagicMock(photo=[MagicMock()], document=None)
        self.assertTrue(is_image_media(msg_photo))

        msg_img_doc = MagicMock(photo=[], document=MagicMock(mime_type="image/jpeg"))
        self.assertTrue(is_image_media(msg_img_doc))

        msg_pdf_doc = MagicMock(
            photo=[], document=MagicMock(mime_type="application/pdf")
        )
        self.assertFalse(is_image_media(msg_pdf_doc))

    @patch("heathen_ledger.handlers.receipt.send_response")
    async def test_ticket_command_no_photo(self, mock_send_response):
        update = MagicMock()
        context = MagicMock()
        update.message.photo = []
        update.message.document = None
        update.message.reply_to_message = None

        await ticket_command_handler(update, context)

        mock_send_response.assert_awaited_once()
        text = mock_send_response.call_args[0][2]
        self.assertIn("To parse a receipt", text)

    @patch("heathen_ledger.handlers.receipt.get_receipt_parser")
    @patch("heathen_ledger.handlers.receipt.send_response")
    async def test_ticket_command_missing_gemini_key(
        self, mock_send_response, mock_get_parser
    ):
        mock_get_parser.side_effect = ValueError("No API key provided")
        update = MagicMock()
        context = MagicMock()
        update.message.photo = [MagicMock()]
        update.message.document = None

        await ticket_command_handler(update, context)

        mock_send_response.assert_awaited_once()
        text = mock_send_response.call_args[0][2]
        self.assertIn("GEMINI_API_KEY", text)
        self.assertIn("not configured", text)

    @patch("heathen_ledger.handlers.receipt.ReceiptService.process_receipt_image")
    @patch("heathen_ledger.handlers.receipt.send_response")
    async def test_ticket_command_photo_in_message(
        self, mock_send_response, mock_process_image
    ):
        mock_receipt = Receipt(
            items=[ReceiptItem(name="Pizza", price=12.0)], total=12.0
        )
        mock_process_image.return_value = (mock_receipt, "1. Pizza — 12.00")

        update = MagicMock()
        context = MagicMock()
        update.message.photo = [MagicMock()]
        update.message.document = None
        update.effective_chat.id = 12345

        await ticket_command_handler(update, context)

        mock_process_image.assert_awaited_once_with(
            bot=context.bot, media_message=update.message, chat_id=12345
        )
        mock_send_response.assert_awaited_once()
        text = mock_send_response.call_args[0][2]
        self.assertEqual(text, "1. Pizza — 12.00")

    @patch("heathen_ledger.handlers.receipt.ReceiptService.process_receipt_image")
    @patch("heathen_ledger.handlers.receipt.send_response")
    async def test_ticket_command_reply_to_photo(
        self, mock_send_response, mock_process_image
    ):
        mock_receipt = Receipt(
            items=[ReceiptItem(name="Burger", price=15.0)], total=15.0
        )
        mock_process_image.return_value = (mock_receipt, "1. Burger — 15.00")

        update = MagicMock()
        context = MagicMock()
        update.message.photo = []
        update.message.document = None

        reply_to = MagicMock()
        reply_to.photo = [MagicMock()]
        reply_to.document = None
        update.message.reply_to_message = reply_to
        update.effective_chat.id = 9999

        await ticket_command_handler(update, context)

        mock_process_image.assert_awaited_once_with(
            bot=context.bot, media_message=reply_to, chat_id=9999
        )
        mock_send_response.assert_awaited_once()
        text = mock_send_response.call_args[0][2]
        self.assertEqual(text, "1. Burger — 15.00")

    @patch("heathen_ledger.handlers.receipt.ReceiptService.process_receipt_image")
    @patch("heathen_ledger.handlers.receipt.send_response")
    async def test_ticket_photo_handler_private_chat(
        self, mock_send_response, mock_process_image
    ):
        mock_receipt = Receipt(items=[ReceiptItem(name="Coffee", price=2.0)], total=2.0)
        mock_process_image.return_value = (mock_receipt, "1. Coffee — 2.00")

        update = MagicMock()
        context = MagicMock()
        update.message.photo = [MagicMock()]
        update.message.document = None
        update.message.caption = None
        update.effective_chat.type = ChatType.PRIVATE
        update.effective_chat.id = 555

        await ticket_photo_handler(update, context)

        mock_process_image.assert_awaited_once_with(
            bot=context.bot, media_message=update.message, chat_id=555
        )
        mock_send_response.assert_awaited_once()

    @patch("heathen_ledger.handlers.receipt.ReceiptService.process_receipt_image")
    @patch("heathen_ledger.handlers.receipt.send_response")
    async def test_ticket_photo_handler_group_with_caption(
        self, mock_send_response, mock_process_image
    ):
        mock_receipt = Receipt(items=[ReceiptItem(name="Salad", price=8.0)], total=8.0)
        mock_process_image.return_value = (mock_receipt, "1. Salad — 8.00")

        update = MagicMock()
        context = MagicMock()
        update.message.photo = [MagicMock()]
        update.message.document = None
        update.message.caption = "/ticket please parse this"
        update.effective_chat.type = ChatType.GROUP
        update.effective_chat.id = 777

        await ticket_photo_handler(update, context)

        mock_process_image.assert_awaited_once_with(
            bot=context.bot, media_message=update.message, chat_id=777
        )
        mock_send_response.assert_awaited_once()

    @patch("heathen_ledger.handlers.receipt.ReceiptService.process_receipt_image")
    @patch("heathen_ledger.handlers.receipt.send_response")
    async def test_ticket_photo_handler_group_ignored_if_no_caption(
        self, mock_send_response, mock_process_image
    ):
        update = MagicMock()
        context = MagicMock()
        context.bot.username = "HeathenLedgerBot"
        update.message.photo = [MagicMock()]
        update.message.document = None
        update.message.caption = "Just a photo with friends"
        update.message.entities = []
        update.message.caption_entities = []
        update.effective_chat.type = ChatType.GROUP
        update.effective_chat.id = 777

        await ticket_photo_handler(update, context)

        mock_process_image.assert_not_called()
        mock_send_response.assert_not_called()

    @patch("heathen_ledger.handlers.receipt.is_bot_mentioned", return_value=True)
    @patch("heathen_ledger.handlers.receipt.ReceiptService.process_receipt_image")
    @patch("heathen_ledger.handlers.receipt.send_response")
    async def test_ticket_mention_handler_success(
        self, mock_send_response, mock_process_image, mock_is_bot_mentioned
    ):
        mock_receipt = Receipt(
            items=[ReceiptItem(name="Pasta", price=14.0)], total=14.0
        )
        mock_process_image.return_value = (mock_receipt, "1. Pasta — 14.00")

        update = MagicMock()
        context = MagicMock()
        reply_to = MagicMock()
        reply_to.photo = [MagicMock()]
        reply_to.document = None
        update.message.reply_to_message = reply_to
        update.effective_chat.id = 888

        await ticket_mention_handler(update, context)

        mock_process_image.assert_awaited_once()
        mock_send_response.assert_awaited_once()

    @patch("heathen_ledger.handlers.voice_mention_handler")
    @patch("heathen_ledger.handlers.ticket_mention_handler")
    async def test_reply_mention_dispatcher(
        self, mock_ticket_mention, mock_voice_mention
    ):
        update_voice = MagicMock()
        context = MagicMock()
        update_voice.message.reply_to_message.voice = MagicMock()
        update_voice.message.reply_to_message.audio = None
        update_voice.message.reply_to_message.photo = None
        update_voice.message.reply_to_message.document = None

        await reply_mention_dispatcher(update_voice, context)
        mock_voice_mention.assert_awaited_once_with(update_voice, context)
        mock_ticket_mention.assert_not_called()

        mock_voice_mention.reset_mock()
        mock_ticket_mention.reset_mock()

        update_photo = MagicMock()
        update_photo.message.reply_to_message.voice = None
        update_photo.message.reply_to_message.audio = None
        update_photo.message.reply_to_message.photo = [MagicMock()]
        update_photo.message.reply_to_message.document = None

        await reply_mention_dispatcher(update_photo, context)
        mock_ticket_mention.assert_awaited_once_with(update_photo, context)
        mock_voice_mention.assert_not_called()

    @patch("heathen_ledger.handlers.receipt.ReceiptService.process_receipt_image")
    @patch("heathen_ledger.handlers.receipt.send_response")
    async def test_ticket_processing_exception_handled(
        self, mock_send_response, mock_process_image
    ):
        mock_process_image.side_effect = RuntimeError("API timeout")
        update = MagicMock()
        context = MagicMock()
        update.message.photo = [MagicMock()]
        update.message.document = None

        await ticket_command_handler(update, context)

        mock_send_response.assert_awaited_once()
        text = mock_send_response.call_args[0][2]
        self.assertIn("Failed to parse receipt image", text)
        self.assertIn("API timeout", text)


if __name__ == "__main__":
    unittest.main()
