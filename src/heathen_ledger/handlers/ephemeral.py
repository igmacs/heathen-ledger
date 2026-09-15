"""Ephemeral message handler proof of concept."""

import logging
from telegram import Update
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def ephemeral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ephemeral or /test_ephemeral command by responding with an ephemeral message."""
    if not update.effective_message or not update.effective_user:
        return

    chat = update.effective_chat
    user = update.effective_user
    user_name = user.first_name or (f"@{user.username}" if user.username else "there")
    is_group = chat is not None and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

    if is_group:
        text = (
            f"👻 *Ephemeral Message Proof of Concept*\n\n"
            f"Hello, *{user_name}*! This message is **ephemeral**.\n\n"
            f"• 👁️ **Visibility:** Visible *only to you* and the bot in this group.\n"
            f"• 🔒 **Privacy:** Other group members cannot see this response.\n"
            f"• 🆔 **Target User ID:** `{user.id}`\n\n"
            f"_Powered by Telegram Bot API `ephemeral_message_parameters`._"
        )
        try:
            await update.effective_message.reply_text(
                text,
                parse_mode="Markdown",
                api_kwargs={
                    "ephemeral_message_parameters": {
                        "receiver_user_id": user.id,
                    }
                },
            )
        except BadRequest as e:
            logger.warning(
                "Failed to send ephemeral message in group %s: %s",
                getattr(chat, "id", None),
                e,
            )
            await update.effective_message.reply_text(
                f"⚠️ *Ephemeral message error:* `{e}`\n\n"
                f"Telegram reported an error sending ephemeral parameters in this chat.",
                parse_mode="Markdown",
            )
    else:
        # Private chat or non-group chat
        text = (
            f"👻 *Ephemeral Message Proof of Concept*\n\n"
            f"Hello, *{user_name}*!\n\n"
            f"In a private 1-on-1 chat with the bot, all messages are already private to you.\n\n"
            f"Ephemeral messages are specifically designed for **group chats**, where the bot can whisper "
            f"private replies (like individual balance summaries, sensitive warnings, or confirmations) "
            f"to a single member without cluttering the group conversation for everyone else.\n\n"
            f"👉 *Try sending `/ephemeral` in a group chat where this bot is present to test it in action!*"
        )
        try:
            await update.effective_message.reply_text(
                text,
                parse_mode="Markdown",
                api_kwargs={
                    "ephemeral_message_parameters": {
                        "receiver_user_id": user.id,
                    }
                },
            )
        except BadRequest:
            await update.effective_message.reply_text(text, parse_mode="Markdown")
