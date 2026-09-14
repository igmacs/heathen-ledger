"""Domain and service layer exceptions."""


class LedgerServiceError(Exception):
    """Base exception for service layer business logic errors."""

    pass


class UserNotFoundError(LedgerServiceError):
    """Raised when a specified user cannot be resolved in the group."""

    def __init__(self, username: str) -> None:
        self.username = username
        super().__init__(
            f"I don't know who @{username} is yet! "
            "They need to send a message in this group first or be registered with /register."
        )


class ValidationError(LedgerServiceError):
    """Raised when validation fails (e.g. no participants left to split with)."""

    pass


class PermissionDeniedError(LedgerServiceError):
    """Raised when a user attempts an unauthorized action."""

    pass
