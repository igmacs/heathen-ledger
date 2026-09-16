import re
from typing import Union, List, Dict, Any

from ..dto import ParsedPaybackCommand, ParseErrorResult
from .amount import AmountParser


class PaybackCommandParser:
    """Parses /payback command messages into ParsedPaybackCommand."""

    @classmethod
    def parse(cls, text: str) -> Union[ParsedPaybackCommand, ParseErrorResult]:
        """Parses a /payback command to extract direct payment details."""
        cleaned_text = re.sub(
            r"^/payback(?:_persistent)?(?:@\w+)?(?:\s+|$)",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        mentions: List[Dict[str, Any]] = []
        for match in re.finditer(r"@(\w+)", cleaned_text):
            mentions.append(
                {
                    "username": match.group(1).lower(),
                    "start": match.start(),
                    "end": match.end(),
                }
            )

        amount_match = re.search(r"\b(\d+(?:\.\d{1,2})?)\b", cleaned_text)
        if not amount_match:
            return ParseErrorResult("No valid amount found in the message.")

        amount_cents = AmountParser.parse_cents(amount_match.group(1))
        if amount_cents is None:
            return ParseErrorResult("No valid amount found in the message.")

        if len(mentions) == 1:
            payer = None
            payee = mentions[0]["username"]
        elif len(mentions) >= 2:
            payer = mentions[0]["username"]
            payee = mentions[1]["username"]
        else:
            return ParseErrorResult(
                "Must mention at least the recipient (payee) of the payback."
            )

        return ParsedPaybackCommand(
            payer_username=payer,
            payee_username=payee,
            amount=amount_cents,
        )
