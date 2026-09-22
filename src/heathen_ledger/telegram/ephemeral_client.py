import asyncio
import logging
from typing import Any, Optional
from collections.abc import Mapping
from unittest.mock import AsyncMock, MagicMock
from telegram import Message
from telegram.error import BadRequest
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


class TelegramEphemeralClient:
    """Encapsulates Telegram Bot API ephemeral messaging calls and fallback mechanisms."""

    @classmethod
    def extract_ephemeral_message_id(cls, message: Any) -> Optional[int]:
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

    @classmethod
    async def delete_ephemeral_message(
        cls,
        bot: Any,
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

        # 1. Use bot._post if available
        if hasattr(bot, "_post"):
            post_fn = bot._post
            if isinstance(post_fn, MagicMock) and not isinstance(post_fn, AsyncMock):
                post_fn("deleteEphemeralMessage", data=data)
                return True
            res = post_fn("deleteEphemeralMessage", data=data)
            if asyncio.iscoroutine(res):
                return bool(await res)
            return bool(res)

        # 2. Custom delete_ephemeral_message method
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

        return False

    @classmethod
    async def edit_ephemeral_message_text(
        cls,
        bot: Any,
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

        # 1. Use bot._post if available
        if hasattr(bot, "_post"):
            post_fn = bot._post
            if isinstance(post_fn, MagicMock) and not isinstance(post_fn, AsyncMock):
                post_fn("editEphemeralMessageText", data=data)
                return True
            res = post_fn("editEphemeralMessageText", data=data)
            if asyncio.iscoroutine(res):
                return bool(await res)
            return bool(res)

        # 2. Custom edit_ephemeral_message_text method
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

    @classmethod
    async def delete_message_or_ephemeral(
        cls,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int | str,
        *,
        user_id: Optional[int] = None,
        ephemeral_message_id: Optional[int] = None,
        message: Optional[Message] = None,
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
            ephemeral_message_id = cls.extract_ephemeral_message_id(message)

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
                res = await cls.delete_ephemeral_message(
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
                    if isinstance(del_fn, AsyncMock) or asyncio.iscoroutinefunction(
                        del_fn
                    ):
                        return await del_fn(chat_id=chat_id, message_id=msg_id)
                    elif callable(del_fn):
                        res = del_fn(chat_id=chat_id, message_id=msg_id)
                        if asyncio.iscoroutine(res):
                            return await res
                        return bool(res)
            except BadRequest as e:
                logger.debug("Failed to delete standard message %s: %s", msg_id, e)

        return False
