import os
import sys
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.receipt import (
    Receipt,
    ReceiptItem,
    ReceiptImageDownloader,
)
from heathen_ledger.services import ReceiptService, ValidationError


class TestReceiptImageDownloader(unittest.IsolatedAsyncioTestCase):
    async def test_download_from_photo(self):
        bot = MagicMock()
        mock_file = MagicMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=b"fake_image_bytes")
        bot.get_file = AsyncMock(return_value=mock_file)

        mock_photo_small = MagicMock(file_id="photo_small")
        mock_photo_large = MagicMock(file_id="photo_large")

        message = MagicMock()
        message.photo = [mock_photo_small, mock_photo_large]
        message.document = None

        image_bytes, mime_type = await ReceiptImageDownloader.download(bot, message)
        self.assertEqual(image_bytes, b"fake_image_bytes")
        self.assertEqual(mime_type, "image/jpeg")
        bot.get_file.assert_called_once_with("photo_large")

    async def test_download_from_image_document(self):
        bot = MagicMock()
        mock_file = MagicMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=b"png_bytes")
        bot.get_file = AsyncMock(return_value=mock_file)

        mock_doc = MagicMock(file_id="doc_123", mime_type="image/png")
        message = MagicMock()
        message.photo = None
        message.document = mock_doc

        image_bytes, mime_type = await ReceiptImageDownloader.download(bot, message)
        self.assertEqual(image_bytes, b"png_bytes")
        self.assertEqual(mime_type, "image/png")
        bot.get_file.assert_called_once_with("doc_123")

    async def test_download_from_non_image_document_raises(self):
        bot = MagicMock()
        mock_doc = MagicMock(file_id="doc_123", mime_type="application/pdf")
        message = MagicMock()
        message.photo = None
        message.document = mock_doc

        with self.assertRaises(ValueError) as ctx:
            await ReceiptImageDownloader.download(bot, message)
        self.assertIn("Expected an image", str(ctx.exception))

    async def test_download_no_media_raises(self):
        bot = MagicMock()
        message = MagicMock()
        message.photo = None
        message.document = None

        with self.assertRaises(ValueError) as ctx:
            await ReceiptImageDownloader.download(bot, message)
        self.assertIn("does not contain photo", str(ctx.exception))


class TestReceiptService(unittest.IsolatedAsyncioTestCase):
    def test_format_price(self):
        self.assertEqual(ReceiptService.format_price(10.5, "€"), "10.50 €")
        self.assertEqual(ReceiptService.format_price(10.5, "$"), "$10.50")
        self.assertEqual(ReceiptService.format_price(10.5, "EUR"), "10.50 EUR")
        self.assertEqual(ReceiptService.format_price(10.5, None), "10.50")

    def test_format_receipt_breakdown_full(self):
        receipt = Receipt(
            merchant="Pizzeria Bella",
            date="2026-09-18",
            currency="€",
            items=[
                ReceiptItem(name="Margherita", price=9.0, quantity=1),
                ReceiptItem(name="Beer", price=10.0, quantity=2),
            ],
            subtotal=19.0,
            tax=1.9,
            tip=2.0,
            total=22.9,
        )
        formatted = ReceiptService.format_receipt_breakdown(receipt)
        self.assertIn("🧾 *Receipt Breakdown*", formatted)
        self.assertIn("Pizzeria Bella", formatted)
        self.assertIn("(2026-09-18)", formatted)
        self.assertIn("1. Margherita — 9.00 €", formatted)
        self.assertIn("2. Beer #1 — 5.00 €", formatted)
        self.assertIn("3. Beer #2 — 5.00 €", formatted)
        self.assertIn("• *Subtotal:* 19.00 €", formatted)
        self.assertIn("• *Tax:* 1.90 €", formatted)
        self.assertIn("• *Tip:* 2.00 €", formatted)
        self.assertIn("• *Total:* 22.90 €", formatted)

    def test_format_receipt_breakdown_empty_items(self):
        receipt = Receipt(
            merchant=None,
            items=[],
            total=15.0,
            currency="$",
        )
        formatted = ReceiptService.format_receipt_breakdown(receipt)
        self.assertIn("No itemized lines could be detected", formatted)
        self.assertIn("*Total:* $15.00", formatted)

    async def test_process_receipt_image_success(self):
        bot = MagicMock()
        bot.send_chat_action = AsyncMock()
        message = MagicMock()
        message.photo = [MagicMock(file_id="photo_1")]
        message.document = None

        mock_receipt = Receipt(
            merchant="Cafe",
            items=[ReceiptItem(name="Coffee", price=2.5, quantity=1)],
            total=2.5,
            currency="€",
        )

        with patch(
            "heathen_ledger.services.receipt_service.ReceiptImageDownloader.download",
            AsyncMock(return_value=(b"img_bytes", "image/jpeg")),
        ), patch(
            "heathen_ledger.services.receipt_service.get_receipt_parser"
        ) as mock_get_parser:
            mock_parser = MagicMock()
            mock_parser.parse = AsyncMock(return_value=mock_receipt)
            mock_get_parser.return_value = mock_parser

            receipt, text = await ReceiptService.process_receipt_image(
                bot, message, chat_id=123
            )
            self.assertEqual(receipt, mock_receipt)
            self.assertIn("1. Coffee — 2.50 €", text)
            bot.send_chat_action.assert_called_once()

    async def test_process_receipt_image_no_media(self):
        bot = MagicMock()
        message = MagicMock()
        message.photo = None
        message.document = None

        with self.assertRaises(ValidationError):
            await ReceiptService.process_receipt_image(bot, message)

    def test_session_lifecycle_and_claiming(self):
        ReceiptService.clear_sessions()
        receipt = Receipt(
            merchant="Osteria",
            items=[ReceiptItem("Pizza", 12.0), ReceiptItem("Beer", 4.0)],
            total=16.0,
            currency="€",
        )
        session = ReceiptService.create_ticket_session(
            chat_id=123,
            creator_id=456,
            creator_name="Ignacio",
            receipt=receipt,
            token="tkt99",
        )
        self.assertIsNotNone(session)
        self.assertEqual(ReceiptService.get_session("tkt99"), session)

        # Toggle me
        s, added = ReceiptService.toggle_item_me(
            token="tkt99", item_idx=0, user_id=1, display_name="Alice", username="alice"
        )
        self.assertTrue(added)
        self.assertEqual(len(s.items[0].participants), 1)

        # Toggle done
        s, done = ReceiptService.toggle_item_done("tkt99", 0)
        self.assertTrue(done)
        self.assertTrue(s.items[0].is_completed)

        # Assign external
        s = ReceiptService.assign_external_member("tkt99", 1, "Carlos Guest")
        self.assertIn("ext:carlos guest", s.items[1].participants)

        # Build rich message
        html, kb = ReceiptService.build_ticket_rich_message("tkt99")
        self.assertIn("Osteria", html)
        self.assertIsNotNone(kb)

        # Build split message
        md, kb_split, shares, rich_html = ReceiptService.build_split_summary_message(
            "tkt99"
        )
        self.assertIn("Bill Split Summary", md)
        self.assertIn("Bill Split Summary", rich_html)
        self.assertEqual(len(shares), 2)

    def test_record_ticket_expense_executes_command(self):
        ReceiptService.clear_sessions()
        receipt = Receipt(
            merchant="Pizzeria",
            items=[ReceiptItem("Pizza", 10.0)],
            total=10.0,
            currency="€",
        )
        session = ReceiptService.create_ticket_session(
            chat_id=123,
            creator_id=1,
            creator_name="Payer",
            receipt=receipt,
            token="tok_rec",
        )
        session.toggle_participant(0, user_id=1, display_name="Payer", username="payer")

        db_session = MagicMock()
        mock_group = MagicMock(id=10, members=[])

        with patch(
            "heathen_ledger.services.receipt_service.GroupRepository"
        ) as mock_grp_repo_cls, patch(
            "heathen_ledger.services.receipt_service.CommandDispatcher.execute"
        ) as mock_exec:
            mock_grp_repo = MagicMock()
            mock_grp_repo.get_by_telegram_id.return_value = mock_group
            mock_grp_repo_cls.return_value = mock_grp_repo

            mock_exec.return_value = ("Expense recorded", MagicMock())

            text, markup = ReceiptService.record_ticket_expense(
                token="tok_rec",
                db_session=db_session,
                payer_id=1,
                payer_username="payer",
                payer_first_name="Payer",
                chat_id=123,
            )
            self.assertEqual(text, "Expense recorded")
            mock_exec.assert_called_once()
            cmd_sent = mock_exec.call_args[1]["command_str"]
            self.assertIn("/pay 10.00 for Pizzeria by me split me:10.00", cmd_sent)
            # Session should be popped
            self.assertIsNone(ReceiptService.get_session("tok_rec"))


if __name__ == "__main__":
    unittest.main()
