import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes

from ..database import with_db_session
from .common import send_response

logger = logging.getLogger(__name__)


@with_db_session
async def start_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Send a greeting and introduction when the command /start is issued."""
    await send_response(
        update,
        context,
        "👋 **Hello! I am Heathen Ledger.**\n\n"
        '_*"This group deserves a better class of ledger, and I’m gonna give it to ‘em."*_\n\n'
        "I help you track and settle shared expenses in group chats. Type /help to see all available commands.",
        parse_mode="Markdown",
    )


# Backward-compatible alias
start = start_command
