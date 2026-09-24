import re
from .amount import AmountParser


class UserTokenParser:
    """Parses individual user tokens like '@alice', '@bob:30', 'me', 'me:25.50'."""

    TOKEN_REGEX = re.compile(r"(?:@(\w+)|(me))(?::(\d+(?:\.\d{1,2})?))?", re.IGNORECASE)

    @classmethod
    def parse_token(cls, token: str) -> tuple[str, int | None] | None:
        """Parses a user token.

        Returns (username_or_me, amount_in_cents_or_none), or None if invalid.
        """
        clean_token = token.strip().rstrip(",")
        match = cls.TOKEN_REGEX.fullmatch(clean_token)
        if not match:
            return None
        username = (match.group(1) or match.group(2)).lower()
        amount_str = match.group(3)
        amount = AmountParser.parse_cents(amount_str) if amount_str else None
        return username, amount
