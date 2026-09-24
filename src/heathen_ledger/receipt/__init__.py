"""Receipt photo parsing and processing package."""

from .base import ReceiptParser, Receipt, ReceiptItem, expand_receipt_items
from .gemini import GeminiReceiptParser
from .image_downloader import ReceiptImageDownloader
from .pending_store import (
    PendingTicketSession,
    PendingTicketStore,
    TicketItemState,
    TicketParticipant,
    extract_initials,
)


def get_receipt_parser(
    provider: str = "gemini",
    api_key: str | None = None,
) -> ReceiptParser:
    """Factory function to get a ReceiptParser instance for the configured provider."""
    if provider.lower() == "gemini":
        return GeminiReceiptParser(api_key=api_key)
    raise ValueError(f"Unsupported receipt provider: '{provider}'")


__all__ = [
    "ReceiptParser",
    "Receipt",
    "ReceiptItem",
    "GeminiReceiptParser",
    "ReceiptImageDownloader",
    "get_receipt_parser",
    "expand_receipt_items",
    "PendingTicketSession",
    "PendingTicketStore",
    "TicketItemState",
    "TicketParticipant",
    "extract_initials",
]
