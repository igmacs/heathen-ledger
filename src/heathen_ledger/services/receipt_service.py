"""Service layer for receipt photo parsing and itemization."""

import logging
from typing import Optional, Tuple
from telegram import Bot, Message
from telegram.constants import ChatAction

from ..receipt import (
    Receipt,
    ReceiptImageDownloader,
    get_receipt_parser,
)
from .exceptions import ValidationError

logger = logging.getLogger(__name__)


class ReceiptService:
    """Service orchestrating receipt image downloading, OCR parsing, and formatting."""

    @classmethod
    def format_price(cls, amount: float, currency: Optional[str] = None) -> str:
        """Format an amount with currency symbol or code."""
        if not currency:
            return f"{amount:.2f}"
        if currency in ("$", "£", "¥"):
            return f"{currency}{amount:.2f}"
        return f"{amount:.2f} {currency}"

    @classmethod
    def format_receipt_breakdown(cls, receipt: Receipt) -> str:
        """Format a parsed receipt into a human-readable Markdown summary."""
        lines = []
        header = "🧾 *Receipt Breakdown*"
        if receipt.merchant:
            header += f"\n📍 *{receipt.merchant}*"
        if receipt.date:
            header += f" _({receipt.date})_"
        lines.append(header)
        lines.append("")

        if not receipt.items:
            lines.append("⚠️ _No itemized lines could be detected on this receipt._")
            if receipt.total is not None:
                lines.append(
                    f"\n*Total:* {cls.format_price(receipt.total, receipt.currency)}"
                )
            return "\n".join(lines)

        for idx, item in enumerate(receipt.items, 1):
            qty_str = (
                f" (x{item.quantity})" if item.quantity and item.quantity > 1 else ""
            )
            formatted_price = cls.format_price(item.price, receipt.currency)
            lines.append(f"{idx}. {item.name}{qty_str} — {formatted_price}")

        summary_lines = []
        if receipt.subtotal is not None:
            summary_lines.append(
                f"• *Subtotal:* {cls.format_price(receipt.subtotal, receipt.currency)}"
            )
        if receipt.tax is not None:
            summary_lines.append(
                f"• *Tax:* {cls.format_price(receipt.tax, receipt.currency)}"
            )
        if receipt.tip is not None:
            summary_lines.append(
                f"• *Tip:* {cls.format_price(receipt.tip, receipt.currency)}"
            )
        if receipt.total is not None:
            summary_lines.append(
                f"• *Total:* {cls.format_price(receipt.total, receipt.currency)}"
            )

        if summary_lines:
            lines.append("\n" + "─" * 20)
            lines.extend(summary_lines)

        return "\n".join(lines)

    @classmethod
    async def process_receipt_image(
        cls,
        bot: Bot,
        media_message: Message,
        chat_id: Optional[int] = None,
    ) -> Tuple[Receipt, str]:
        """Download, parse via Gemini, and return (Receipt, formatted_markdown)."""
        has_media = bool(
            getattr(media_message, "photo", None)
            or getattr(media_message, "document", None)
        )
        if not has_media:
            raise ValidationError("Message does not contain a photo or image document.")

        if chat_id is not None:
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass

        image_bytes, mime_type = await ReceiptImageDownloader.download(
            bot, media_message
        )
        parser = get_receipt_parser()
        receipt = await parser.parse(image_bytes, mime_type=mime_type)
        formatted_text = cls.format_receipt_breakdown(receipt)
        return receipt, formatted_text
