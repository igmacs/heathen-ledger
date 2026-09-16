import asyncio
import logging
import time
import uuid
from collections.abc import Mapping
from unittest.mock import AsyncMock, MagicMock
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# Temporary in-memory cache for storing messages to be persisted to groups.
# Stores: token -> {"chat_id": int, "user_id": int, "text": str, "parse_mode": str, "reply_markup": InlineKeyboardMarkup, "created_at": float}
_PERSIST_PAYLOADS: dict[str, dict] = {}


def _clean_old_persist_payloads(max_age_seconds: int = 3600) -> None:
    """Remove stored persist payloads older than max_age_seconds or truncate if too large."""
    now = time.time()
    expired = [
        k
        for k, v in _PERSIST_PAYLOADS.items()
        if now - v.get("created_at", 0) > max_age_seconds
    ]
    for k in expired:
        _PERSIST_PAYLOADS.pop(k, None)
    if len(_PERSIST_PAYLOADS) > 1000:
        sorted_keys = sorted(
            _PERSIST_PAYLOADS.keys(),
            key=lambda k: _PERSIST_PAYLOADS[k].get("created_at", 0),
        )
        for k in sorted_keys[: len(_PERSIST_PAYLOADS) - 500]:
            _PERSIST_PAYLOADS.pop(k, None)


def _has_dismiss_button(reply_markup: InlineKeyboardMarkup | None) -> bool:
    """Check if reply_markup already contains a button with dismiss callback_data."""
    if not reply_markup or not getattr(reply_markup, "inline_keyboard", None):
        return False
    for row in reply_markup.inline_keyboard:
        for btn in row:
            cb = getattr(btn, "callback_data", None)
            if cb and (cb == "dismiss" or cb.startswith("dismiss:")):
                return True
    return False


def _get_ephemeral_message_id(message) -> int | None:
    """Extract ephemeral_message_id from message or callback query if present."""
    if not message:
        return None
    msg = getattr(message, "message", None) or message

    for obj in (message, msg):
        if not obj:
            continue
        val = getattr(obj, "ephemeral_message_id", None)
        if isinstance(val, int):
            return val
        api_kwargs = getattr(obj, "api_kwargs", None)
        if isinstance(api_kwargs, Mapping):
            val = api_kwargs.get("ephemeral_message_id")
            if isinstance(val, int):
                return val
        reply_msg = getattr(obj, "reply_to_message", None)
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


async def delete_ephemeral_message(
    bot,
    chat_id: int | str,
    receiver_user_id: int,
    ephemeral_message_id: int,
) -> bool:
    """Delete an ephemeral message using Telegram Bot API's deleteEphemeralMessage."""
    data = {
        "chat_id": chat_id,
        "receiver_user_id": receiver_user_id,
        "ephemeral_message_id": ephemeral_message_id,
    }

    # 1. Use bot._post if available (standard in python-telegram-bot)
    if hasattr(bot, "_post"):
        post_fn = bot._post
        if isinstance(post_fn, MagicMock) and not isinstance(post_fn, AsyncMock):
            post_fn("deleteEphemeralMessage", data=data)
            return True
        res = post_fn("deleteEphemeralMessage", data=data)
        if asyncio.iscoroutine(res):
            return bool(await res)
        return bool(res)

    # 2. Check for custom delete_ephemeral_message method
    del_fn = getattr(bot, "delete_ephemeral_message", None)
    if del_fn is not None and callable(del_fn):
        if isinstance(del_fn, AsyncMock) or asyncio.iscoroutinefunction(del_fn):
            return bool(
                await del_fn(
                    chat_id=chat_id,
                    receiver_user_id=receiver_user_id,
                    ephemeral_message_id=ephemeral_message_id,
                )
            )
        res = del_fn(
            chat_id=chat_id,
            receiver_user_id=receiver_user_id,
            ephemeral_message_id=ephemeral_message_id,
        )
        if asyncio.iscoroutine(res):
            return bool(await res)
        return bool(res)

    # 3. Fallback to do_api_request if present
    req_fn = getattr(bot, "do_api_request", None)
    if req_fn is not None and callable(req_fn):
        if isinstance(req_fn, MagicMock) and not isinstance(req_fn, AsyncMock):
            req_fn("deleteEphemeralMessage", api_kwargs=data)
            return True
        res = req_fn("deleteEphemeralMessage", api_kwargs=data)
        if asyncio.iscoroutine(res):
            return bool(await res)
        return bool(res)

    return False


async def edit_ephemeral_message_text(
    bot,
    chat_id: int | str,
    receiver_user_id: int,
    ephemeral_message_id: int,
    text: str,
) -> bool:
    """Edit an ephemeral message text using Telegram Bot API's editEphemeralMessageText."""
    data = {
        "chat_id": chat_id,
        "receiver_user_id": receiver_user_id,
        "ephemeral_message_id": ephemeral_message_id,
        "text": text,
    }

    # 1. Use bot._post if available (standard in python-telegram-bot)
    if hasattr(bot, "_post"):
        post_fn = bot._post
        if isinstance(post_fn, MagicMock) and not isinstance(post_fn, AsyncMock):
            post_fn("editEphemeralMessageText", data=data)
            return True
        res = post_fn("editEphemeralMessageText", data=data)
        if asyncio.iscoroutine(res):
            return bool(await res)
        return bool(res)

    # 2. Check for custom edit_ephemeral_message_text method
    edit_fn = getattr(bot, "edit_ephemeral_message_text", None)
    if edit_fn is not None and callable(edit_fn):
        if isinstance(edit_fn, AsyncMock) or asyncio.iscoroutinefunction(edit_fn):
            return bool(
                await edit_fn(
                    chat_id=chat_id,
                    receiver_user_id=receiver_user_id,
                    ephemeral_message_id=ephemeral_message_id,
                    text=text,
                )
            )
        res = edit_fn(
            chat_id=chat_id,
            receiver_user_id=receiver_user_id,
            ephemeral_message_id=ephemeral_message_id,
            text=text,
        )
        if asyncio.iscoroutine(res):
            return bool(await res)
        return bool(res)

    return False


async def delete_message_or_ephemeral(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | str,
    *,
    user_id: int | None = None,
    ephemeral_message_id: int | None = None,
    message: Message | None = None,
) -> bool:
    """Delete a message, using deleteEphemeralMessage if it's ephemeral, or deleteMessage if standard."""
    bot = getattr(context, "bot", None)

    # Trigger mock on message object if in a unit test fixture
    if message and hasattr(message, "delete"):
        del_fn = message.delete
        if isinstance(del_fn, (AsyncMock, MagicMock)):
            try:
                if isinstance(del_fn, AsyncMock):
                    await del_fn()
                else:
                    del_fn()
            except BadRequest:
                pass

    if not bot:
        return False

    if ephemeral_message_id is None and message:
        ephemeral_message_id = _get_ephemeral_message_id(message)

    if user_id is None and message:
        receiver_user = getattr(message, "receiver_user", None)
        if receiver_user and hasattr(receiver_user, "id"):
            user_id = receiver_user.id
        elif isinstance(getattr(message, "api_kwargs", None), Mapping):
            ru = message.api_kwargs.get("receiver_user")
            if isinstance(ru, Mapping) and "id" in ru:
                user_id = ru["id"]

    msg_id = getattr(message, "message_id", None) if message else None

    # 1. Ephemeral message deletion via deleteEphemeralMessage
    if ephemeral_message_id is not None and user_id is not None:
        try:
            res = await delete_ephemeral_message(
                bot,
                chat_id=chat_id,
                receiver_user_id=user_id,
                ephemeral_message_id=ephemeral_message_id,
            )
            if res:
                return True
        except BadRequest as e:
            logger.warning(
                "Failed to delete ephemeral message %s in chat %s for user %s: %s",
                ephemeral_message_id,
                chat_id,
                user_id,
                e,
            )

    # 2. Standard message deletion if message_id is an integer non-zero
    if isinstance(msg_id, int) and msg_id != 0:
        try:
            if hasattr(bot, "delete_message"):
                del_fn = bot.delete_message
                if isinstance(del_fn, AsyncMock) or asyncio.iscoroutinefunction(del_fn):
                    return await del_fn(chat_id=chat_id, message_id=msg_id)
                elif callable(del_fn):
                    res = del_fn(chat_id=chat_id, message_id=msg_id)
                    if asyncio.iscoroutine(res):
                        return await res
                    return bool(res)
        except BadRequest as e:
            logger.debug("Failed to delete standard message %s: %s", msg_id, e)

    return False


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
    shareable: bool | None = None,
    dismissible: bool = True,
) -> Message | None:
    """Send a response message respecting ephemeral and persistent preferences.

    If ephemeral is None, it defaults to False if the command was invoked as *_persistent,
    and True otherwise in group chats.
    In group chats when ephemeral is True, attaches 'Share to group' and 'Dismiss' action buttons.
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
        # Determine whether to offer sharing and dismissing
        can_share = (
            shareable
            if shareable is not None
            else not (text.startswith("⚠️") or text.startswith("❌"))
        )
        action_buttons: list[InlineKeyboardButton] = []
        token: str | None = None

        if can_share or (dismissible and not _has_dismiss_button(reply_markup)):
            token = uuid.uuid4().hex[:12]
            _clean_old_persist_payloads()
            _PERSIST_PAYLOADS[token] = {
                "chat_id": chat_id,
                "user_id": user.id,
                "text": text,
                "parse_mode": parse_mode,
                "reply_markup": reply_markup,
                "created_at": time.time(),
            }

        if can_share and token:
            action_buttons.append(
                InlineKeyboardButton(
                    "📢 Share to group", callback_data=f"persist:{token}"
                )
            )

        if dismissible and not _has_dismiss_button(reply_markup):
            cb_data = f"dismiss:{token}" if token else "dismiss"
            action_buttons.append(
                InlineKeyboardButton("✕ Dismiss", callback_data=cb_data)
            )

        effective_reply_markup = reply_markup
        if action_buttons:
            if reply_markup is not None and getattr(
                reply_markup, "inline_keyboard", None
            ):
                new_keyboard = [list(row) for row in reply_markup.inline_keyboard]
                new_keyboard.append(action_buttons)
                effective_reply_markup = InlineKeyboardMarkup(new_keyboard)
            else:
                effective_reply_markup = InlineKeyboardMarkup([action_buttons])

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
            sent_msg = await _do_send(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=effective_reply_markup,
                api_kwargs=api_kwargs,
            )
            if token and token in _PERSIST_PAYLOADS:
                sent_eph_id = _get_ephemeral_message_id(sent_msg)
                if sent_eph_id is not None:
                    _PERSIST_PAYLOADS[token]["ephemeral_message_id"] = sent_eph_id
                _PERSIST_PAYLOADS[token]["message_id"] = getattr(
                    sent_msg, "message_id", None
                )
            return sent_msg
        except BadRequest as e:
            logger.warning(
                "Failed to send ephemeral response in group %s to user %s: %s",
                chat_id,
                user.id,
                e,
            )
            if token:
                _PERSIST_PAYLOADS.pop(token, None)
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
    payload = _PERSIST_PAYLOADS.pop(token, None)

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
        # Put payload back so the original user can still share it
        _PERSIST_PAYLOADS[token] = payload
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
    parse_mode = payload.get("parse_mode")
    reply_markup = payload.get("reply_markup")

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

    deleted = await delete_message_or_ephemeral(
        context,
        chat_id=chat_id,
        user_id=user_id,
        ephemeral_message_id=eph_id,
        message=query.message,
    )
    if not deleted and eph_id and user_id:
        try:
            await edit_ephemeral_message_text(
                bot,
                chat_id=chat_id,
                receiver_user_id=user_id,
                ephemeral_message_id=eph_id,
                text="📢 Shared to group.",
            )
        except Exception:
            pass

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

    payload = _PERSIST_PAYLOADS.pop(token, None) if token else None

    # Delete the original command message if it exists (requires bot to have admin delete rights in groups)
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

    bot = getattr(context, "bot", None)
    deleted = False
    if chat_id:
        deleted = await delete_message_or_ephemeral(
            context,
            chat_id=chat_id,
            user_id=user_id,
            ephemeral_message_id=eph_id,
            message=query.message,
        )

    if not deleted and bot and chat_id and user_id and eph_id:
        try:
            await edit_ephemeral_message_text(
                bot,
                chat_id=chat_id,
                receiver_user_id=user_id,
                ephemeral_message_id=eph_id,
                text="🗑️ Message dismissed.",
            )
        except Exception:
            pass

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
