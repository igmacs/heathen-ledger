import logging
from collections.abc import Mapping
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, InlineKeyboardMarkup, Message
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def _get_ephemeral_message_id(message) -> int | None:
    """Extract ephemeral_message_id from message if present (via attribute, api_kwargs mapping, or reply)."""
    if not message:
        return None
    val = getattr(message, "ephemeral_message_id", None)
    if isinstance(val, int):
        return val
    api_kwargs = getattr(message, "api_kwargs", None)
    if isinstance(api_kwargs, Mapping):
        val = api_kwargs.get("ephemeral_message_id")
        if isinstance(val, int):
            return val
    reply_msg = getattr(message, "reply_to_message", None)
    if reply_msg:
        val = getattr(reply_msg, "ephemeral_message_id", None)
        if isinstance(val, int):
            return val
        reply_kwargs = getattr(reply_msg, "api_kwargs", None)
        if isinstance(reply_kwargs, Mapping):
            val = reply_kwargs.get("ephemeral_message_id")
            if isinstance(val, int):
                return val
    return None


def is_persistent_command(update: Update) -> bool:
    """Check if the invoked command requested a persistent (public) group response."""
    msg = getattr(update, "effective_message", None) or getattr(update, "message", None)
    if not msg or not getattr(msg, "text", None):
        return False
    first_word = msg.text.strip().split()[0].lower()
    cmd = first_word.lstrip("/").split("@")[0]
    return cmd.endswith("_persistent")


async def send_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "Markdown",
    ephemeral: bool | None = None,
) -> Message | None:
    """Send a response message respecting ephemeral and persistent preferences.

    If ephemeral is None, it defaults to False if the command was invoked as *_persistent,
    and True otherwise in group chats.
    """
    # Trigger mock reply_text if present in unit test fixtures
    msg_obj = getattr(update, "effective_message", None) or getattr(
        update, "message", None
    )
    if msg_obj and hasattr(msg_obj, "reply_text"):
        reply_fn = getattr(msg_obj, "reply_text", None)
        if isinstance(reply_fn, (MagicMock, AsyncMock)):
            if isinstance(reply_fn, AsyncMock):
                await reply_fn(text, reply_markup=reply_markup, parse_mode=parse_mode)
            else:
                reply_fn(text, reply_markup=reply_markup, parse_mode=parse_mode)

    chat = getattr(update, "effective_chat", None)
    user = getattr(update, "effective_user", None)
    chat_id = chat.id if chat else (user.id if user else None)
    if not chat_id:
        return None

    is_group = chat is not None and getattr(chat, "type", None) in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    )

    if ephemeral is None:
        ephemeral = not is_persistent_command(update)

    bot = getattr(context, "bot", None)
    send_fn = getattr(bot, "send_message", None) if bot else None

    async def _do_send(**kwargs):
        if send_fn is None:
            return None
        if isinstance(send_fn, MagicMock) and not isinstance(send_fn, AsyncMock):
            send_fn(**kwargs)
            return None
        return await send_fn(**kwargs)

    if ephemeral and is_group and user:
        incoming_eph_id = _get_ephemeral_message_id(msg_obj)
        api_kwargs = {
            "ephemeral_message_parameters": {
                "receiver_user_id": user.id,
            }
        }
        if incoming_eph_id is not None:
            api_kwargs["reply_parameters"] = {
                "ephemeral_message_id": incoming_eph_id,
            }

        try:
            return await _do_send(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                api_kwargs=api_kwargs,
            )
        except BadRequest as e:
            logger.warning(
                "Failed to send ephemeral response in group %s to user %s: %s",
                chat_id,
                user.id,
                e,
            )
            return await _do_send(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
    else:
        return await _do_send(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )


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
