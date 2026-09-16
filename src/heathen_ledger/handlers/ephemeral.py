"""Ephemeral message handler proof of concept."""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def _get_ephemeral_message_id(message) -> int | None:
    """Extract ephemeral_message_id from message if present (via attribute or api_kwargs)."""
    if not message:
        return None
    ephemeral_id = getattr(message, "ephemeral_message_id", None)
    if isinstance(ephemeral_id, int):
        return ephemeral_id
    api_kwargs = getattr(message, "api_kwargs", None)
    if isinstance(api_kwargs, dict):
        val = api_kwargs.get("ephemeral_message_id")
        if isinstance(val, int):
            return val
    return None


async def ephemeral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ephemeral or /test_ephemeral command by responding with an ephemeral message."""
    if not update.effective_message or not update.effective_user:
        return

    chat = update.effective_chat
    user = update.effective_user
    user_name = user.first_name or (f"@{user.username}" if user.username else "there")
    is_group = chat is not None and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "⚡ Test via Button (No Admin Required)",
                    callback_data="ephemeral_cb",
                )
            ]
        ]
    )

    if is_group:
        text = (
            f"👻 *Ephemeral Message Proof of Concept*\n\n"
            f"Hello, *{user_name}*! This message is **ephemeral**.\n\n"
            f"• 👁️ **Visibility:** Visible *only to you* and the bot in this group.\n"
            f"• 🔒 **Privacy:** Other group members cannot see this response.\n"
            f"• 🆔 **Target User ID:** `{user.id}`\n\n"
            f"_Powered by Telegram Bot API `ephemeral_message_parameters`._"
        )

        api_kwargs = {
            "ephemeral_message_parameters": {
                "receiver_user_id": user.id,
            }
        }
        incoming_ephemeral_id = _get_ephemeral_message_id(update.effective_message)
        if incoming_ephemeral_id is not None:
            api_kwargs["reply_parameters"] = {
                "ephemeral_message_id": incoming_ephemeral_id,
            }

        try:
            await update.effective_message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=keyboard,
                api_kwargs=api_kwargs,
            )
        except BadRequest as e:
            logger.warning(
                "Failed to send ephemeral message in group %s: %s",
                getattr(chat, "id", None),
                e,
            )
            admin_explanation = (
                "Telegram requires the bot to be a **Group Administrator** to send ephemeral messages "
                "in response to standard chat commands.\n\n"
                "**Non-admin bots** can only send ephemeral messages when:\n"
                "1. Responding to an inline button within 15 seconds (using `callback_query_id`), or\n"
                "2. Replying to an incoming ephemeral command (with `ephemeral_message_id`).\n\n"
                "👉 *Promote the bot to Group Admin to enable direct command responses, "
                "or tap the button below to test non-admin ephemeral messaging via button callback:*"
            )
            await update.effective_message.reply_text(
                f"⚠️ *Ephemeral Message Error:* `{e}`\n\n{admin_explanation}",
                parse_mode="Markdown",
                reply_markup=keyboard,
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
                reply_markup=keyboard,
                api_kwargs={
                    "ephemeral_message_parameters": {
                        "receiver_user_id": user.id,
                    }
                },
            )
        except BadRequest:
            await update.effective_message.reply_text(
                text, parse_mode="Markdown", reply_markup=keyboard
            )


async def ephemeral_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle inline button callback to demonstrate non-admin ephemeral messaging via callback_query_id."""
    query = update.callback_query
    if not query or not query.from_user:
        return

    user = query.from_user
    user_name = user.first_name or (f"@{user.username}" if user.username else "there")
    chat = update.effective_chat

    if not chat:
        await query.answer()
        return

    text = (
        f"👻 *Ephemeral Message via Callback Query*\n\n"
        f"Hello, *{user_name}*! This message is **ephemeral**.\n\n"
        f"• 👁️ **Visibility:** Visible *only to you* and the bot in this group.\n"
        f"• ⚡ **No Admin Required:** Because this was triggered by an inline button callback, "
        f"the bot sends this within 15 seconds using `callback_query_id`!\n"
        f"• 🆔 **Target User ID:** `{user.id}`\n\n"
        f"_Powered by Telegram Bot API `ephemeral_message_parameters`._"
    )

    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            parse_mode="Markdown",
            api_kwargs={
                "ephemeral_message_parameters": {
                    "receiver_user_id": user.id,
                    "callback_query_id": query.id,
                }
            },
        )
    except BadRequest as e:
        logger.warning("Failed to send ephemeral callback message: %s", e)
        await query.answer(f"Failed to send ephemeral message: {e}", show_alert=True)
        return

    await query.answer()
