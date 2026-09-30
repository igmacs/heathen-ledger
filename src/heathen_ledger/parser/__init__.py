"""Command parsing package: clause parsers, pay command parser, and payback parser."""

from ..domain.calculations import simplify_debts, split_amount_equally
from ..dto import (
    CommandParseError,
    ParsedPaybackCommand,
    ParsedPayCommand,
    ParseErrorResult,
    SplitSpec,
)
from ..formatters import (
    generate_balances_summary,
    generate_history_rich_html,
    generate_history_summary,
    generate_settlements_summary,
)
from .amount import AmountParser
from .date_clause import DateClauseParser
from .pay_parser import PayCommandParser
from .payback_parser import PaybackCommandParser
from .payer_clause import PayerClauseParser
from .split_clause import SplitClauseParser
from .user_token import UserTokenParser

__all__ = [
    "AmountParser",
    "UserTokenParser",
    "DateClauseParser",
    "SplitClauseParser",
    "PayerClauseParser",
    "PayCommandParser",
    "PaybackCommandParser",
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
