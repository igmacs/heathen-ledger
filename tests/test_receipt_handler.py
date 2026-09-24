import asyncio
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from telegram.constants import ChatType

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger import crud
from heathen_ledger.handlers import reply_mention_dispatcher
from heathen_ledger.handlers.receipt import (
    is_image_media,
    ticket_callback_handler,
    ticket_command_handler,
    ticket_external_reply_handler,
    ticket_mention_handler,
    ticket_photo_handler,
)
from heathen_ledger.receipt import Receipt, ReceiptItem
from heathen_ledger.services import ReceiptService

from tests.base import BaseDatabaseTestCase


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
        kwargs = mock_send_response.call_args.kwargs
        self.assertIn("Pizza", kwargs.get("rich_html", ""))
        self.assertIsNotNone(kwargs.get("reply_markup"))
        self.assertFalse(kwargs.get("ephemeral"))

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
        kwargs = mock_send_response.call_args.kwargs
        self.assertIn("Burger", kwargs.get("rich_html", ""))
        self.assertIsNotNone(kwargs.get("reply_markup"))
        self.assertFalse(kwargs.get("ephemeral"))

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
        self, mock_send_response, mock_process_image, _mock_is_bot_mentioned
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


class TestReceiptTicketCallbacks(BaseDatabaseTestCase):
    def setUp(self):
        super().setUp()
        ReceiptService.get_store().clear()
        self.receipt = Receipt(
            items=[
                ReceiptItem(name="Pizza", price=10.0),
                ReceiptItem(name="Beer", price=5.0),
            ],
            total=15.0,
            merchant="Bistro",
        )
        self.session_obj = ReceiptService.create_ticket_session(
            chat_id=self.group.telegram_chat_id,
            creator_id=self.alice.telegram_id,
            creator_name="Alice",
            receipt=self.receipt,
        )
        self.token = self.session_obj.token

    def test_callback_toggle_me(self):
        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:m:{self.token}:0",
        )
        update.callback_query.from_user.id = self.alice.telegram_id
        update.callback_query.from_user.first_name = "Alice"
        update.callback_query.from_user.username = "alice"
        update.callback_query.from_user.last_name = None
        context = MagicMock()

        asyncio.run(ticket_callback_handler(update, context))

        session = ReceiptService.get_session(self.token)
        self.assertIn(f"tg:{self.alice.telegram_id}", session.items[0].participants)
        update.callback_query.answer.assert_called()

        # Toggle again to unclaim
        asyncio.run(ticket_callback_handler(update, context))
        self.assertNotIn(f"tg:{self.alice.telegram_id}", session.items[0].participants)

    def test_callback_toggle_done(self):
        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:d:{self.token}:0",
        )
        context = MagicMock()

        asyncio.run(ticket_callback_handler(update, context))
        session = ReceiptService.get_session(self.token)
        self.assertTrue(session.items[0].is_completed)

        # Toggle again
        asyncio.run(ticket_callback_handler(update, context))
        self.assertFalse(session.items[0].is_completed)

    def test_callback_assign_person_selector_and_checklist_toggle(self):
        # 1. Person selector menu
        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:asgn:{self.token}",
        )
        context = MagicMock()
        asyncio.run(ticket_callback_handler(update, context))
        update.callback_query.answer.assert_called()

        # 2. Open checklist for Bob
        update_psel = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:psel:{self.token}:tg:{self.bob.telegram_id}",
        )
        asyncio.run(ticket_callback_handler(update_psel, context))
        update_psel.callback_query.answer.assert_called()

        # 3. Toggle item 0 for Bob in checklist
        update_ptog = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:ptog:{self.token}:tg:{self.bob.telegram_id}:0",
        )
        asyncio.run(ticket_callback_handler(update_ptog, context))
        session = ReceiptService.get_session(self.token)
        self.assertIn(f"tg:{self.bob.telegram_id}", session.items[0].participants)
        self.assertEqual(
            session.items[0].participants[f"tg:{self.bob.telegram_id}"].display_name,
            "Bob",
        )

        # 4. Toggle item 0 off for Bob
        asyncio.run(ticket_callback_handler(update_ptog, context))
        self.assertNotIn(f"tg:{self.bob.telegram_id}", session.items[0].participants)

    def test_callback_assign_group_user_legacy(self):
        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:asgn_usr:{self.token}:0:{self.bob.telegram_id}",
        )
        context = MagicMock()
        asyncio.run(ticket_callback_handler(update, context))

        session = ReceiptService.get_session(self.token)
        self.assertIn(f"tg:{self.bob.telegram_id}", session.items[0].participants)

    def test_callback_assign_new_external_and_reply(self):
        # Step 1: Click add external user from Person Selector
        update_cb = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:asgn_new:{self.token}",
        )
        context = MagicMock()
        context.user_data = {}
        asyncio.run(ticket_callback_handler(update_cb, context))

        self.assertIn("pending_ext_ticket", context.user_data)
        self.assertEqual(context.user_data["pending_ext_ticket"]["token"], self.token)

        # Step 2: Send text with the external name
        update_msg = self.create_mock_message_update("Dave")
        asyncio.run(ticket_external_reply_handler(update_msg, context))

        self.assertNotIn("pending_ext_ticket", context.user_data)
        session = ReceiptService.get_session(self.token)
        self.assertIn("ext:dave", session.external_participants)
        self.assertEqual(session.external_participants["ext:dave"].display_name, "Dave")
        update_msg.message.reply_text.assert_called_once()
        self.assertIn("Registered guest", update_msg.message.reply_text.call_args[0][0])

        # Step 3: Now Dave is toggled on items via checklist
        update_ptog = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:ptog:{self.token}:ext:dave:1",
        )
        asyncio.run(ticket_callback_handler(update_ptog, context))
        self.assertIn("ext:dave", session.items[1].participants)

    def test_callback_assign_external_reply_cancel(self):
        context = MagicMock()
        context.user_data = {"pending_ext_ticket": {"token": self.token, "item_idx": 0}}
        update_msg = self.create_mock_message_update("/cancel")
        asyncio.run(ticket_external_reply_handler(update_msg, context))

        self.assertNotIn("pending_ext_ticket", context.user_data)
        update_msg.message.reply_text.assert_called_once()
        self.assertIn("Cancelled", update_msg.message.reply_text.call_args[0][0])

    def test_callback_finish_split_no_claims_alert(self):
        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:fin:{self.token}",
        )
        context = MagicMock()
        asyncio.run(ticket_callback_handler(update, context))

        update.callback_query.answer.assert_called_once()
        self.assertTrue(update.callback_query.answer.call_args.kwargs.get("show_alert"))
        self.assertIn(
            "No items have been claimed yet",
            update.callback_query.answer.call_args[0][0],
        )

    def test_callback_finish_split_and_record_expense(self):
        # Claim both items: Alice takes Pizza (10.0), Bob takes Beer (5.0)
        ReceiptService.toggle_item_me(
            token=self.token,
            item_idx=0,
            user_id=self.alice.telegram_id,
            display_name="Alice",
            username="alice",
        )
        ReceiptService.toggle_item_me(
            token=self.token,
            item_idx=1,
            user_id=self.bob.telegram_id,
            display_name="Bob",
            username="bob",
        )

        # Step 1: Finish split view
        update_fin = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:fin:{self.token}",
        )
        context = MagicMock()
        asyncio.run(ticket_callback_handler(update_fin, context))
        update_fin.callback_query.answer.assert_called()

        # Step 2: Record expense
        update_rec = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:record:{self.token}",
        )
        update_rec.callback_query.from_user.id = self.alice.telegram_id
        update_rec.callback_query.from_user.username = "alice"
        update_rec.callback_query.from_user.first_name = "Alice"

        asyncio.run(ticket_callback_handler(update_rec, context))

        update_rec.callback_query.answer.assert_called()
        # Verify session is consumed/removed
        self.assertIsNone(ReceiptService.get_session(self.token))

        # Verify expense recorded in db
        expenses = crud.get_group_expenses(self.db_session, self.group.id)
        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0].amount, 1500)
        self.assertEqual(expenses[0].payer_id, self.alice.id)

    def test_callback_back_and_cancel(self):
        # Back
        update_back = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:back:{self.token}",
        )
        context = MagicMock()
        asyncio.run(ticket_callback_handler(update_back, context))
        update_back.callback_query.answer.assert_called()

        # Cancel
        update_cancel = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"tkt:cancel:{self.token}",
        )
        asyncio.run(ticket_callback_handler(update_cancel, context))
        update_cancel.callback_query.answer.assert_called()
        self.assertIsNone(ReceiptService.get_session(self.token))

    def test_callback_expired_session(self):
        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data="tkt:m:expired_tok:0",
        )
        context = MagicMock()
        asyncio.run(ticket_callback_handler(update, context))
        update.callback_query.answer.assert_called_once()
        self.assertTrue(update.callback_query.answer.call_args.kwargs.get("show_alert"))
        self.assertIn("expired", update.callback_query.answer.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
