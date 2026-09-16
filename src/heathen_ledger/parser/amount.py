import re
from typing import Optional


class AmountParser:
    """Parses numeric currency strings into integer cents."""

    AMOUNT_REGEX = re.compile(r"(\d+(?:\.\d{1,2})?)")

    @classmethod
    def parse_cents(cls, amount_str: str) -> Optional[int]:
        """Parse a numeric string (integer or up to 2 decimals) into integer cents.

        Returns None if the string does not match valid currency format.
        """
        match = cls.AMOUNT_REGEX.fullmatch(amount_str.strip())
        if not match:
            return None
        val = match.group(1)
        if "." in val:
            parts = val.split(".")
            dollars = int(parts[0])
            cents_part = parts[1]
            cents = (
                int(cents_part) * 10 if len(cents_part) == 1 else int(cents_part[:2])
            )
            return dollars * 100 + cents
        return int(val) * 100
