from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ReceiptItem:
    """Represents a single line item on a parsed receipt."""

    name: str
    price: float
    quantity: int = 1


@dataclass
class Receipt:
    """Represents a parsed receipt with line items and totals."""

    items: List[ReceiptItem] = field(default_factory=list)
    merchant: Optional[str] = None
    date: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    tip: Optional[float] = None
    total: Optional[float] = None
    raw_response: Optional[str] = None


class ReceiptParser(ABC):
    """Abstract base class defining the interface for receipt parsing."""

    @abstractmethod
    async def parse(
        self,
        image_data: bytes,
        mime_type: str = "image/jpeg",
    ) -> Receipt:
        """Parse raw image bytes of a receipt into structured Receipt data.

        Args:
            image_data: Raw bytes of the image file.
            mime_type: MIME type of the image (e.g. image/jpeg, image/png).

        Returns:
            Receipt object containing items, totals, and metadata.
        """
        pass
