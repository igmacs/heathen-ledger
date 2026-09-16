import datetime
from typing import Optional, Tuple
from ..dto import ParseErrorResult


class DateClauseParser:
    """Parses date clauses such as 'today', 'yesterday', or ISO dates ('YYYY-MM-DD')."""

    @classmethod
    def parse_clause(
        cls, clause_text: str
    ) -> Tuple[Optional[datetime.date], Optional[ParseErrorResult]]:
        """Parses an 'on' clause into a datetime.date object.

        Returns (date, None) on success, or (None, ParseErrorResult) on error.
        """
        on_raw = clause_text.strip().lower()
        if on_raw == "today":
            return datetime.date.today(), None
        elif on_raw == "yesterday":
            return datetime.date.today() - datetime.timedelta(days=1), None
        else:
            try:
                return datetime.date.fromisoformat(on_raw), None
            except ValueError:
                return None, ParseErrorResult(
                    f"Invalid date format '{clause_text.strip()}'. "
                    "Expected YYYY-MM-DD, 'today', or 'yesterday'."
                )
