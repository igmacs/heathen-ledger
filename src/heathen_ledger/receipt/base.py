from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ReceiptItem:
    """Represents a single line item on a parsed receipt."""

    name: str
    price: float
    quantity: int = 1


def expand_receipt_items(items: List[ReceiptItem]) -> List[ReceiptItem]:
    """Expand repeated items (quantity > 1) into individual single-quantity line items.

    Allocates prices penny-perfectly so that sum(expanded_prices) == original_price.
    """
    expanded: List[ReceiptItem] = []
    for item in items:
        if item.quantity <= 1:
            expanded.append(ReceiptItem(name=item.name, price=item.price, quantity=1))
        else:
            base_price = round(item.price / item.quantity, 2)
            allocated = round(base_price * (item.quantity - 1), 2)
            last_price = round(item.price - allocated, 2)

            for i in range(item.quantity):
                unit_price = last_price if i == item.quantity - 1 else base_price
                expanded.append(
                    ReceiptItem(
                        name=f"{item.name} #{i + 1}",
                        price=unit_price,
                        quantity=1,
                    )
                )
    return expanded


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

    def expand_items(self) -> List[ReceiptItem]:
        """Return items with any repeated items (quantity > 1) expanded to single units."""
        return expand_receipt_items(self.items)


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
