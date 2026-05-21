import logging
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def dismiss_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback query when a dismiss/OK button is clicked to delete the message."""
    query = update.callback_query
    if not query:
        return

    if query.data != "dismiss":
        return

    # Delete the original command message if it exists (requires bot to have admin delete rights in groups)
    if query.message and query.message.reply_to_message:
        try:
            await query.message.reply_to_message.delete()
        except BadRequest as e:
            logger.warning(f"Failed to delete original command message: {e}")

    # Delete the bot's error message
    if query.message:
        try:
            await query.message.delete()
        except BadRequest as e:
            logger.warning(f"Failed to delete error message: {e}")

    await query.answer()
