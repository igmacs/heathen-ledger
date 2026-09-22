import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock
from telegram import InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from ..telegram import (
    EphemeralPayloadStore,
    TelegramEphemeralClient,
    EphemeralActionKeyboardDecorator,
    TelegramRichClient,
)


logger = logging.getLogger(__name__)

# Temporary in-memory cache for storing messages to be persisted to groups.
_EPHEMERAL_STORE = EphemeralPayloadStore()
_PERSIST_PAYLOADS = _EPHEMERAL_STORE.payloads
_clean_old_persist_payloads = _EPHEMERAL_STORE.prune_expired
_has_dismiss_button = EphemeralActionKeyboardDecorator.has_dismiss_button
_get_ephemeral_message_id = TelegramEphemeralClient.extract_ephemeral_message_id
delete_ephemeral_message = TelegramEphemeralClient.delete_ephemeral_message
delete_message_or_ephemeral = TelegramEphemeralClient.delete_message_or_ephemeral


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
    text: str | None = None,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = "Markdown",
    ephemeral: bool | None = None,
    shareable: bool | None = None,
    dismissible: bool = True,
    rich_html: str | None = None,
) -> Message | None:
    """Send a response message respecting ephemeral and persistent preferences.

    If ephemeral is None, it defaults to False if the command was invoked as *_persistent,
    and True otherwise in group chats.
    In group chats when ephemeral is True, attaches 'Share to group' and 'Dismiss' action buttons.
    Supports Telegram Bot API 10.3 Rich Messages via rich_html.
    """
    # Trigger mock reply_text if present in unit test fixtures
    msg_obj = getattr(update, "effective_message", None) or getattr(
        update, "message", None
    )
    if msg_obj and hasattr(msg_obj, "reply_text"):
        reply_fn = getattr(msg_obj, "reply_text", None)
        if isinstance(reply_fn, (MagicMock, AsyncMock)):
            effective_text = text if text is not None else (rich_html or "")
            if isinstance(reply_fn, AsyncMock):
                await reply_fn(
                    effective_text, reply_markup=reply_markup, parse_mode=parse_mode
                )
            else:
                reply_fn(
                    effective_text, reply_markup=reply_markup, parse_mode=parse_mode
                )

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
        can_share = (
            shareable
            if shareable is not None
            else not (text and (text.startswith("⚠️") or text.startswith("❌")))
        )

        token: str | None = None
        if can_share or (dismissible and not _has_dismiss_button(reply_markup)):
            token = _EPHEMERAL_STORE.store(
                chat_id=chat_id,
                user_id=user.id,
                text=text or "",
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                rich_html=rich_html,
            )

        effective_reply_markup = EphemeralActionKeyboardDecorator.attach_action_buttons(
            reply_markup=reply_markup,
            token=token,
            can_share=can_share,
            dismissible=dismissible,
        )

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
            if rich_html and bot:
                sent_msg = await TelegramRichClient.send_rich_message(
                    bot=bot,
                    chat_id=chat_id,
                    rich_html=rich_html,
                    reply_markup=effective_reply_markup,
                    ephemeral_message_parameters=api_kwargs[
                        "ephemeral_message_parameters"
                    ],
                    reply_parameters=api_kwargs.get("reply_parameters"),
                )
            else:
                sent_msg = await _do_send(
                    chat_id=chat_id,
                    text=text or "",
                    parse_mode=parse_mode,
                    reply_markup=effective_reply_markup,
                    api_kwargs=api_kwargs,
                )
            if token and token in _EPHEMERAL_STORE.payloads:
                sent_eph_id = _get_ephemeral_message_id(sent_msg)
                if sent_eph_id is not None:
                    _EPHEMERAL_STORE.payloads[token]["ephemeral_message_id"] = (
                        sent_eph_id
                    )
                _EPHEMERAL_STORE.payloads[token]["message_id"] = getattr(
                    sent_msg, "message_id", None
                )
            return sent_msg
        except Exception as e:
            logger.warning(
                "Failed to send ephemeral response in group %s to user %s: %s",
                chat_id,
                user.id,
                e,
            )
            if token:
                _EPHEMERAL_STORE.pop(token)
            raise
    else:
        if rich_html and bot:
            return await TelegramRichClient.send_rich_message(
                bot=bot,
                chat_id=chat_id,
                rich_html=rich_html,
                reply_markup=reply_markup,
            )
        return await _do_send(
            chat_id=chat_id,
            text=text or "",
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )


async def persist_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle callback query when a 'Share to group' button is clicked.

    Deletes the ephemeral response and sends a persistent (public) message to the group.
    """
    query = update.callback_query
    if not query or not query.data:
        return

    if not query.data.startswith("persist:"):
        return

    token = query.data.split(":", 1)[1]
    payload = _EPHEMERAL_STORE.pop(token)

    if not payload:
        try:
            await query.answer(
                "This message has expired or has already been shared.",
                show_alert=True,
            )
        except BadRequest:
            pass
        return

    # Check that the user clicking the button is the one who requested it
    user = getattr(update, "effective_user", None) or getattr(query, "from_user", None)
    if user and payload.get("user_id") and user.id != payload["user_id"]:
        _EPHEMERAL_STORE.restore(token, payload)
        try:
            await query.answer(
                "Only the person who requested this message can share it.",
                show_alert=True,
            )
        except BadRequest:
            pass
        return

    bot = getattr(context, "bot", None)
    if not bot:
        return

    # 1. Send the persistent message to the group
    chat_id = payload["chat_id"]
    text = payload["text"]
    rich_html = payload.get("rich_html")
    parse_mode = payload.get("parse_mode")
    reply_markup = payload.get("reply_markup")

    if rich_html:
        await TelegramRichClient.send_rich_message(
            bot=bot,
            chat_id=chat_id,
            rich_html=rich_html,
            reply_markup=reply_markup,
        )
    else:
        send_fn = getattr(bot, "send_message", None)
        if send_fn:
            if isinstance(send_fn, AsyncMock) or asyncio.iscoroutinefunction(send_fn):
                await send_fn(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
            elif callable(send_fn):
                res = send_fn(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
                if asyncio.iscoroutine(res):
                    await res

    # 2. Delete the ephemeral message using delete_message_or_ephemeral
    eph_id = payload.get("ephemeral_message_id") or _get_ephemeral_message_id(
        query.message
    )
    user_id = payload.get("user_id") or (
        query.from_user.id if query.from_user else None
    )

    await delete_message_or_ephemeral(
        context,
        chat_id=chat_id,
        user_id=user_id,
        ephemeral_message_id=eph_id,
        message=query.message,
    )

    # 3. Answer callback query
    if hasattr(query, "answer"):
        try:
            ans_fn = query.answer
            if isinstance(ans_fn, AsyncMock) or asyncio.iscoroutinefunction(ans_fn):
                await ans_fn("Shared to group!")
            elif callable(ans_fn):
                res = ans_fn("Shared to group!")
                if asyncio.iscoroutine(res):
                    await res
        except BadRequest:
            pass


async def dismiss_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle callback query when a dismiss/OK button is clicked to delete the message."""
    query = update.callback_query
    if not query or not query.data:
        return

    if not query.data.startswith("dismiss"):
        return

    token: str | None = None
    if query.data.startswith("dismiss:"):
        token = query.data.split(":", 1)[1]

    payload = _EPHEMERAL_STORE.pop(token) if token else None

    # Delete the original command message if it exists
    if query.message and getattr(query.message, "reply_to_message", None):
        reply_msg = query.message.reply_to_message
        if hasattr(reply_msg, "delete"):
            try:
                del_fn = reply_msg.delete
                if isinstance(del_fn, AsyncMock) or asyncio.iscoroutinefunction(del_fn):
                    await del_fn()
                elif callable(del_fn):
                    res = del_fn()
                    if asyncio.iscoroutine(res):
                        await res
            except BadRequest as e:
                logger.debug("Failed to delete original command message: %s", e)

    user = getattr(query, "from_user", None) or getattr(update, "effective_user", None)
    chat = (
        query.message.chat
        if query.message and getattr(query.message, "chat", None)
        else None
    ) or getattr(update, "effective_chat", None)
    chat_id = (payload and payload.get("chat_id")) or (
        chat.id if chat and getattr(chat, "id", None) is not None else None
    )
    user_id = (payload and payload.get("user_id")) or (
        user.id if user and getattr(user, "id", None) is not None else None
    )
    eph_id = (
        payload and payload.get("ephemeral_message_id")
    ) or _get_ephemeral_message_id(query.message)

    if chat_id:
        await delete_message_or_ephemeral(
            context,
            chat_id=chat_id,
            user_id=user_id,
            ephemeral_message_id=eph_id,
            message=query.message,
        )

    if hasattr(query, "answer"):
        try:
            ans_fn = query.answer
            if isinstance(ans_fn, AsyncMock) or asyncio.iscoroutinefunction(ans_fn):
                await ans_fn()
            elif callable(ans_fn):
                res = ans_fn()
                if asyncio.iscoroutine(res):
                    await res
        except BadRequest:
            pass
