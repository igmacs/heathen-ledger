"""Command parsing package: clause parsers, pay command parser, and payback parser."""

from typing import Any

from ..domain.calculations import split_amount_equally, simplify_debts
from ..formatters import (
    generate_balances_summary,
    generate_settlements_summary,
    generate_history_summary,
    generate_history_rich_html,
)

from ..dto import (
    CommandParseError,
    ParseErrorResult,
    SplitSpec,
    ParsedPayCommand,
    ParsedPaybackCommand,
)
from .amount import AmountParser
from .user_token import UserTokenParser
from .date_clause import DateClauseParser
from .split_clause import SplitClauseParser
from .payer_clause import PayerClauseParser
from .pay_parser import PayCommandParser
from .payback_parser import PaybackCommandParser


def parse_pay_message(text: str) -> dict[str, Any]:
    """Parses a /pay command message to extract expense details.

    Delegates to PayCommandParser.
    """
    return PayCommandParser.parse(text)


def parse_payback_message(text: str) -> dict[str, Any]:
    """Parses a /payback command to extract direct payment details.

    Delegates to PaybackCommandParser.
    """
    return PaybackCommandParser.parse(text)


__all__ = [
    "AmountParser",
    "UserTokenParser",
    "DateClauseParser",
    "SplitClauseParser",
    "PayerClauseParser",
    "PayCommandParser",
    "PaybackCommandParser",
    "parse_pay_message",
    "parse_payback_message",
    "split_amount_equally",
    "simplify_debts",
    "generate_balances_summary",
    "generate_settlements_summary",
    "generate_history_summary",
    "generate_history_rich_html",
    "CommandParseError",
    "ParseErrorResult",
    "SplitSpec",
    "ParsedPayCommand",
    "ParsedPaybackCommand",
]
