"""Ephemeral message handler proof of concept."""

import logging
from collections.abc import Mapping
from telegram import Update
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def _get_ephemeral_message_id(message) -> int | None:
    """Extract ephemeral_message_id from message if present (via attribute, api_kwargs mapping, or reply)."""
    if not message:
        return None
    # 1. Direct attribute
    val = getattr(message, "ephemeral_message_id", None)
    if isinstance(val, int):
        return val
    # 2. api_kwargs mappingproxy or dict
    api_kwargs = getattr(message, "api_kwargs", None)
    if isinstance(api_kwargs, Mapping):
        val = api_kwargs.get("ephemeral_message_id")
        if isinstance(val, int):
            return val
    # 3. Check reply_to_message if user replied to an ephemeral message
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


async def ephemeral_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /ephemeral or /whisper command by responding with an ephemeral message."""
    if not update.effective_message or not update.effective_user:
        return

    chat = update.effective_chat
    user = update.effective_user
    user_name = user.first_name or (f"@{user.username}" if user.username else "there")
    is_group = chat is not None and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)

    if is_group:
        incoming_ephemeral_id = _get_ephemeral_message_id(update.effective_message)
        is_ephemeral_cmd = incoming_ephemeral_id is not None

        cmd_type_label = (
            "🔒 **Ephemeral Command** (Two-way privacy active!)"
            if is_ephemeral_cmd
            else "💬 **Standard Command** (Invoked as regular chat message)"
        )
        id_info = (
            f"• 🆔 **Incoming Ephemeral ID:** `{incoming_ephemeral_id}`\n"
            if is_ephemeral_cmd
            else "• ℹ️ **Incoming Ephemeral ID:** None (sent as standard message)\n"
        )
        admin_note = (
            "• ⚡ **Admin Status:** Not required (replied to incoming ephemeral ID within 15s)."
            if is_ephemeral_cmd
            else "• 🛡️ **Admin Status:** Required for standard message replies without incoming ephemeral ID."
        )

        text = (
            f"👻 *Ephemeral Command Test*\n\n"
            f"Hello, *{user_name}*!\n\n"
            f"• 📥 **Input:** {cmd_type_label}\n"
            f"{id_info}"
            f"• 📤 **Output:** Ephemeral message visible *only to you*.\n"
            f"• 👤 **Target User:** `{user.id}`\n"
            f"{admin_note}\n\n"
            f"_Powered by Telegram Bot API `ephemeral_message_parameters`._"
        )

        api_kwargs = {
            "ephemeral_message_parameters": {
                "receiver_user_id": user.id,
            }
        }
        if incoming_ephemeral_id is not None:
            api_kwargs["reply_parameters"] = {
                "ephemeral_message_id": incoming_ephemeral_id,
            }

        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=text,
                parse_mode="Markdown",
                api_kwargs=api_kwargs,
            )
        except BadRequest as e:
            logger.warning(
                "Failed to send ephemeral message in group %s: %s",
                getattr(chat, "id", None),
                e,
            )
            admin_explanation = (
                "Telegram requires the bot to be a **Group Administrator** to send ephemeral replies "
                "to standard chat messages.\n\n"
                "**To test two-way ephemeral commands without admin rights:**\n"
                "1. Make sure your Telegram app is updated to support Ephemeral Commands (Bot API 10.2+).\n"
                "2. Type `/` in this group and tap `/ephemeral` or `/whisper` from the command menu popup.\n"
                "3. Your Telegram client will send it as an ephemeral command, allowing the bot to reply without admin privileges."
            )
            await update.effective_message.reply_text(
                f"⚠️ *Ephemeral Message Error:* `{e}`\n\n{admin_explanation}",
                parse_mode="Markdown",
            )
    else:
        # Private chat or non-group chat
        text = (
            f"👻 *Ephemeral Command Test*\n\n"
            f"Hello, *{user_name}*!\n\n"
            f"In a private 1-on-1 chat with the bot, all messages are already private to you.\n\n"
            f"Ephemeral commands are designed for **group chats**, where you can type `/ephemeral` or `/whisper` "
            f"and the command remains invisible to other members, with the bot whispering an ephemeral reply directly to you.\n\n"
            f"👉 *Try sending `/ephemeral` or `/whisper` in a group chat where this bot is present to test it in action!*"
        )
        try:
            await context.bot.send_message(
                chat_id=chat.id if chat else user.id,
                text=text,
                parse_mode="Markdown",
                api_kwargs={
                    "ephemeral_message_parameters": {
                        "receiver_user_id": user.id,
                    }
                },
            )
        except BadRequest:
            await update.effective_message.reply_text(text, parse_mode="Markdown")


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
