"""Data Transfer Objects (DTOs) for parsed commands and split configurations."""

import datetime
from dataclasses import dataclass, field


class CommandParseError(Exception):
    """Raised when a command text fails syntax validation or parsing."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class ParseErrorResult:
    """Represents a parsing failure."""

    error: str


@dataclass
class SplitSpec:
    """Split configuration describing how an expense should be divided among participants."""

    mode: str = "all"  # 'all', 'subset', 'except', 'custom'
    participants: list[str] = field(default_factory=list)
    shares: dict[str, int | None] = field(default_factory=dict)
    excluded: list[str] = field(default_factory=list)


@dataclass
class ParsedPayCommand:
    """Structured data extracted from a /pay command."""

    amount: int
    payers: dict[str, int]
    description: str | None = None
    split_spec: SplitSpec = field(default_factory=SplitSpec)
    expense_date: datetime.date | None = None
    payer_username: str | None = None
    participants: list[str] = field(default_factory=list)


@dataclass
class ParsedPaybackCommand:
    """Structured data extracted from a /payback command."""

    payee_username: str
    amount: int
    payer_username: str | None = None
