"""Backward-compatibility facade re-exporting handlers now housed in feature modules."""

from .help import help_command
from .members import members_command
from .registration import (
    _resolve_admin_by_username,
    auto_register,
    register_callback_handler,
    register_command,
)
from .start import start, start_command

__all__ = [
    "_resolve_admin_by_username",
    "auto_register",
    "register_command",
    "register_callback_handler",
    "members_command",
    "start",
    "start_command",
    "help_command",
]
