"""Receipt photo parsing and processing package."""

from typing import Optional
from .base import ReceiptParser, Receipt, ReceiptItem
from .gemini import GeminiReceiptParser
from .image_downloader import ReceiptImageDownloader


def get_receipt_parser(
    provider: str = "gemini",
    api_key: Optional[str] = None,
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
]
