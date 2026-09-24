import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.receipt import (
    GeminiReceiptParser,
    Receipt,
    ReceiptItem,
    ReceiptParser,
    get_receipt_parser,
)


class DummyReceiptParser(ReceiptParser):
    async def parse(self, image_data: bytes, mime_type: str = "image/jpeg") -> Receipt:
        return Receipt(
            merchant="Test Bistro",
            currency="€",
            items=[
                ReceiptItem(name="Pizza", price=12.5, quantity=1),
                ReceiptItem(name="Beer", price=10.0, quantity=2),
            ],
            subtotal=22.5,
            tax=2.25,
            total=24.75,
            raw_response="{}",
        )


class TestReceiptParser(unittest.IsolatedAsyncioTestCase):
    async def test_dummy_implementation(self):
        parser = DummyReceiptParser()
        receipt = await parser.parse(b"dummy image", mime_type="image/jpeg")
        self.assertEqual(receipt.merchant, "Test Bistro")
        self.assertEqual(receipt.currency, "€")
        self.assertEqual(len(receipt.items), 2)
        self.assertEqual(receipt.items[0].name, "Pizza")
        self.assertEqual(receipt.items[0].price, 12.5)
        self.assertEqual(receipt.items[0].quantity, 1)
        self.assertEqual(receipt.items[1].name, "Beer")
        self.assertEqual(receipt.items[1].price, 10.0)
        self.assertEqual(receipt.items[1].quantity, 2)
        self.assertEqual(receipt.total, 24.75)

    def test_receipt_dataclass_defaults(self):
        receipt = Receipt()
        self.assertEqual(receipt.items, [])
        self.assertIsNone(receipt.merchant)
        self.assertIsNone(receipt.currency)
        self.assertIsNone(receipt.total)
        self.assertIsNone(receipt.raw_response)

    def test_gemini_parser_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                GeminiReceiptParser(api_key=None)
            self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    def test_get_receipt_parser_factory(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_key"}):
            parser = get_receipt_parser("gemini")
            self.assertIsInstance(parser, GeminiReceiptParser)

            with self.assertRaises(ValueError) as ctx:
                get_receipt_parser("unsupported_provider")
            self.assertIn("Unsupported receipt provider", str(ctx.exception))

    async def test_gemini_parser_successful_parse(self):
        mock_response = MagicMock()
        mock_response.text = """
        {
            "merchant": "Trattoria Bella",
            "date": "2026-09-18",
            "currency": "EUR",
            "items": [
                {"name": "Margherita Pizza", "quantity": 2, "price": 18.0},
                {"name": "Tiramisu", "quantity": 1, "price": 6.5}
            ],
            "subtotal": 24.5,
            "tax": 2.45,
            "tip": null,
            "total": 26.95
        }
        """

        mock_generate_content = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content

        with patch(
            "heathen_ledger.receipt.gemini.genai.Client", return_value=mock_client
        ):
            parser = GeminiReceiptParser(api_key="fake_key")
            receipt = await parser.parse(b"fake_image_bytes", mime_type="image/jpeg")

            self.assertEqual(receipt.merchant, "Trattoria Bella")
            self.assertEqual(receipt.date, "2026-09-18")
            self.assertEqual(receipt.currency, "EUR")
            self.assertEqual(len(receipt.items), 2)
            self.assertEqual(receipt.items[0].name, "Margherita Pizza")
            self.assertEqual(receipt.items[0].quantity, 2)
            self.assertEqual(receipt.items[0].price, 18.0)
            self.assertEqual(receipt.items[1].name, "Tiramisu")
            self.assertEqual(receipt.items[1].quantity, 1)
            self.assertEqual(receipt.items[1].price, 6.5)
            self.assertEqual(receipt.subtotal, 24.5)
            self.assertEqual(receipt.tax, 2.45)
            self.assertIsNone(receipt.tip)
            self.assertEqual(receipt.total, 26.95)

    async def test_gemini_parser_invalid_json(self):
        mock_response = MagicMock()
        mock_response.text = "This is not valid JSON"

        mock_generate_content = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = mock_generate_content

        with patch(
            "heathen_ledger.receipt.gemini.genai.Client", return_value=mock_client
        ):
            parser = GeminiReceiptParser(api_key="fake_key")
            receipt = await parser.parse(b"fake_image_bytes")

            self.assertEqual(receipt.items, [])
            self.assertEqual(receipt.raw_response, "This is not valid JSON")


if __name__ == "__main__":
    unittest.main()
