import json
import logging
import os

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .base import Receipt, ReceiptItem, ReceiptParser

logger = logging.getLogger(__name__)


class ReceiptItemSchema(BaseModel):
    name: str = Field(description="Short item name or description")
    quantity: int = Field(default=1, description="Quantity of the item")
    price: float = Field(
        description="Total price for this line item (in decimal, e.g. 12.50)"
    )


class ReceiptSchema(BaseModel):
    merchant: str | None = Field(
        None, description="Merchant or restaurant name if detected"
    )
    date: str | None = Field(
        None, description="Receipt date in YYYY-MM-DD format if detected"
    )
    currency: str | None = Field(
        None,
        description="Currency symbol or 3-letter code (e.g. €, $, EUR, USD) if detected",
    )
    items: list[ReceiptItemSchema] = Field(
        description="List of itemized goods or services on the receipt"
    )
    subtotal: float | None = Field(
        None, description="Subtotal amount before tax or tip if listed"
    )
    tax: float | None = Field(None, description="Tax or VAT amount if listed")
    tip: float | None = Field(None, description="Tip or service charge if listed")
    total: float | None = Field(
        None, description="Final total amount paid on the receipt"
    )


class GeminiReceiptParser(ReceiptParser):
    """Google Gemini implementation of ReceiptParser."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No API key provided. Please set the GEMINI_API_KEY environment variable."
            )
        self.model_name = (
            model_name or os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash-lite"
        )
        self.client = genai.Client(api_key=self.api_key)

    async def parse(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
    ) -> Receipt:
        """Parse receipt image bytes into structured Receipt using Gemini."""
        prompt = (
            "You are an AI assistant specialized in analyzing restaurant and store receipts/bills.\n"
            "Analyze this receipt image and extract all individual itemized goods or services.\n\n"
            "Guidelines:\n"
            "1. Extract each distinct item with its name/description, quantity, and total line price.\n"
            "2. If an item has a quantity greater than 1 (e.g., '2 Beers at 5.00 each = 10.00'), set quantity to 2 and price to 10.00.\n"
            "3. Do NOT include subtotal, tax, tip, or total lines in the 'items' list; place them in their respective summary fields.\n"
            "4. Extract the merchant name, date, and currency symbol or code if visible.\n"
            "5. If total is not explicitly printed, calculate it as sum of items (or subtotal + tax + tip).\n"
            "6. Keep item descriptions concise and readable in the receipt's original language.\n"
        )

        image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ReceiptSchema,
        )

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[image_part, prompt],
            config=config,
        )

        raw_text = (response.text or "").strip()
        try:
            data = json.loads(raw_text)
            items_data = data.get("items") or []
            items = [
                ReceiptItem(
                    name=item.get("name", "Item"),
                    price=float(item.get("price", 0.0)),
                    quantity=int(item.get("quantity", 1)),
                )
                for item in items_data
                if item.get("name")
            ]
            return Receipt(
                items=items,
                merchant=data.get("merchant"),
                date=data.get("date"),
                currency=data.get("currency"),
                subtotal=(
                    float(data["subtotal"])
                    if data.get("subtotal") is not None
                    else None
                ),
                tax=float(data["tax"]) if data.get("tax") is not None else None,
                tip=float(data["tip"]) if data.get("tip") is not None else None,
                total=float(data["total"]) if data.get("total") is not None else None,
                raw_response=raw_text,
            )
        except Exception as e:
            logger.warning(
                f"Failed to parse structured JSON from Gemini receipt response: {e}"
            )
            return Receipt(
                items=[],
                raw_response=raw_text,
            )
