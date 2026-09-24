"""Data Transfer Objects (DTOs) for parsed commands and split configurations."""

import datetime
from dataclasses import dataclass, field
from typing import Any


class CommandParseError(Exception):
    """Raised when a command text fails syntax validation or parsing."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class ParseErrorResult:
    """Represents a parsing failure for backwards compatibility with dict inspection."""

    error: str

    def __getitem__(self, item: str) -> Any:
        if item == "error":
            return self.error
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        if item == "error":
            return self.error
        return default

    def __contains__(self, item: str) -> bool:
        return item == "error"

    def __repr__(self) -> str:
        return f"ParseErrorResult(error={self.error!r})"


@dataclass
class SplitSpec:
    """Split configuration describing how an expense should be divided among participants."""

    mode: str = "all"  # 'all', 'subset', 'except', 'custom'
    participants: list[str] = field(default_factory=list)
    shares: dict[str, int | None] = field(default_factory=dict)
    excluded: list[str] = field(default_factory=list)

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


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

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        if item == "error":
            return False
        return hasattr(self, item)


@dataclass
class ParsedPaybackCommand:
    """Structured data extracted from a /payback command."""

    payee_username: str
    amount: int
    payer_username: str | None = None

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: str) -> bool:
        if item == "error":
            return False
        return hasattr(self, item)
