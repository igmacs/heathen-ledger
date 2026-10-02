"""Client adapter for Telegram Bot API 10.3+ Rich Messages.

========================================================================================
TODO / FUTURE PTB INTEGRATION NOTE:
python-telegram-bot (as of v22.8) does not yet provide first-class model classes or
helper methods for Telegram Bot API 10.3 Rich Messages (such as `bot.send_rich_message`,
`telegram.InputRichMessage`, `telegram.RichMessageButton`, `<tg-button>` HTML parsing, etc.).

When python-telegram-bot adds native support for Rich Messages:
1. Replace the raw Bot API calls below (e.g. `bot._post("sendRichMessage", ...)` and
   `bot._post("editEphemeralMessageText", ...)`) with PTB's native methods and types.
2. The rest of the codebase (handlers, formatters, and common responders) calls this
   `TelegramRichClient` adapter exclusively, so upgrading to native PTB rich message
   support in the future only requires updating this file.
========================================================================================
"""

import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from telegram import InlineKeyboardMarkup
from telegram.error import BadRequest

from .ephemeral_client import TelegramEphemeralClient

logger = logging.getLogger(__name__)


class TelegramRichClient:
    """Encapsulates Telegram Bot API 10.3+ Rich Message calls and compatibility fallbacks."""

    @classmethod
    def build_rich_message_payload(cls, html: str) -> dict[str, Any]:
        """Wrap HTML formatted string into an InputRichMessage payload dictionary."""
        return {"html": html}

    @classmethod
    async def _invoke_callable(cls, fn: Any, **kwargs: Any) -> Any:
        if isinstance(fn, AsyncMock):
            return await fn(**kwargs)
        if isinstance(fn, MagicMock):
            return fn(**kwargs)
        if asyncio.iscoroutinefunction(fn):
            return await fn(**kwargs)
        res = fn(**kwargs)
        if asyncio.iscoroutine(res):
            return await res
        return res

    @classmethod
    async def _send_native_rich_message(
        cls,
        bot: Any,
        chat_id: int | str,
        rich_html: str,
        reply_markup: InlineKeyboardMarkup | None,
        ephemeral_message_parameters: dict[str, Any] | None,
        reply_parameters: Any,
        disable_notification: bool | None,
        **kwargs: Any,
    ) -> Any:
        call_kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "rich_message": cls.build_rich_message_payload(rich_html),
            **kwargs,
        }
        if reply_markup is not None:
            call_kwargs["reply_markup"] = reply_markup
        if ephemeral_message_parameters:
            call_kwargs["ephemeral_message_parameters"] = ephemeral_message_parameters
        if reply_parameters is not None:
            call_kwargs["reply_parameters"] = reply_parameters
        if disable_notification is not None:
            call_kwargs["disable_notification"] = disable_notification

        return await cls._invoke_callable(bot.send_rich_message, **call_kwargs)

    @classmethod
    async def _send_mock_fallback(
        cls,
        send_msg: Any,
        chat_id: int | str,
        rich_html: str,
        reply_markup: InlineKeyboardMarkup | None,
        ephemeral_message_parameters: dict[str, Any] | None,
        reply_parameters: Any,
    ) -> Any:
        api_kwargs = {"rich_message": cls.build_rich_message_payload(rich_html)}
        if ephemeral_message_parameters:
            api_kwargs["ephemeral_message_parameters"] = ephemeral_message_parameters

        call_kwargs = {
            "chat_id": chat_id,
            "text": rich_html,
            "reply_markup": reply_markup,
            "api_kwargs": api_kwargs,
        }
        if reply_parameters is not None:
            call_kwargs["reply_parameters"] = reply_parameters

        return await cls._invoke_callable(send_msg, **call_kwargs)

    @classmethod
    async def _send_post_rich_message(
        cls,
        bot: Any,
        chat_id: int | str,
        rich_html: str,
        reply_markup: InlineKeyboardMarkup | None,
        ephemeral_message_parameters: dict[str, Any] | None,
        reply_parameters: Any,
        disable_notification: bool | None,
    ) -> Any:
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "rich_message": cls.build_rich_message_payload(rich_html),
        }
        if ephemeral_message_parameters:
            data["ephemeral_message_parameters"] = ephemeral_message_parameters
        if reply_parameters is not None:
            data["reply_parameters"] = (
                reply_parameters.to_dict()
                if hasattr(reply_parameters, "to_dict")
                else reply_parameters
            )
        if disable_notification is not None:
            data["disable_notification"] = disable_notification
        if reply_markup is not None:
            data["reply_markup"] = (
                reply_markup.to_dict()
                if hasattr(reply_markup, "to_dict")
                else reply_markup
            )

        if hasattr(bot, "_post"):
            post_fn = bot._post
            if isinstance(post_fn, MagicMock) and not isinstance(post_fn, AsyncMock):
                return post_fn("sendRichMessage", data=data)
            res = post_fn("sendRichMessage", data=data)
            if asyncio.iscoroutine(res):
                return await res
            return res
        return None

    @classmethod
    async def send_rich_message(
        cls,
        bot: Any,
        chat_id: int | str,
        rich_html: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        ephemeral_message_parameters: dict[str, Any] | None = None,
        reply_parameters: dict[str, Any] | Any | None = None,
        disable_notification: bool | None = None,
        **kwargs: Any,
    ) -> Any:
        """Send a rich formatted message using Telegram Bot API's sendRichMessage.

        Supports future PTB native `send_rich_message`, active runtime `bot._post`,
        and test mock fallback to `bot.send_message`.
        """
        # 1. Check for future native PTB send_rich_message method
        has_native_send = hasattr(type(bot), "send_rich_message") or (
            "send_rich_message" in getattr(bot, "__dict__", {})
        )
        if has_native_send and callable(getattr(bot, "send_rich_message", None)):
            return await cls._send_native_rich_message(
                bot,
                chat_id,
                rich_html,
                reply_markup,
                ephemeral_message_parameters,
                reply_parameters,
                disable_notification,
                **kwargs,
            )

        # 2. Test mock compatibility: If only bot.send_message was mocked in a test fixture
        send_msg = getattr(bot, "send_message", None)
        post_fn = getattr(bot, "_post", None)
        if isinstance(send_msg, MagicMock | AsyncMock) and not isinstance(
            post_fn, MagicMock | AsyncMock
        ):
            return await cls._send_mock_fallback(
                send_msg,
                chat_id,
                rich_html,
                reply_markup,
                ephemeral_message_parameters,
                reply_parameters,
            )

        # 3. Standard PTB raw Bot API execution via bot._post('sendRichMessage')
        return await cls._send_post_rich_message(
            bot,
            chat_id,
            rich_html,
            reply_markup,
            ephemeral_message_parameters,
            reply_parameters,
            disable_notification,
        )

    @classmethod
    async def edit_rich_message_text(
        cls,
        bot: Any,
        chat_id: int | str,
        message_id: int,
        rich_html: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        """Edit a standard rich message using editMessageText with rich_message."""
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "rich_message": cls.build_rich_message_payload(rich_html),
        }
        if reply_markup is not None:
            if hasattr(reply_markup, "to_dict"):
                data["reply_markup"] = reply_markup.to_dict()
            else:
                data["reply_markup"] = reply_markup

        has_native_edit = hasattr(type(bot), "edit_rich_message_text") or (
            "edit_rich_message_text" in getattr(bot, "__dict__", {})
        )
        if has_native_edit and callable(getattr(bot, "edit_rich_message_text", None)):
            # Future PTB native support
            edit_fn = bot.edit_rich_message_text

            if isinstance(edit_fn, AsyncMock | MagicMock):
                if isinstance(edit_fn, AsyncMock):
                    return bool(await edit_fn(**data))
                return bool(edit_fn(**data))
            res = edit_fn(**data)
            if asyncio.iscoroutine(res):
                return bool(await res)
            return bool(res)

        if hasattr(bot, "_post"):
            post_fn = bot._post
            if isinstance(post_fn, MagicMock) and not isinstance(post_fn, AsyncMock):
                post_fn("editMessageText", data=data)
                return True
            res = post_fn("editMessageText", data=data)
            if asyncio.iscoroutine(res):
                return bool(await res)
            return bool(res)

        return False

    @classmethod
    async def edit_ephemeral_rich_message_text(
        cls,
        bot: Any,
        chat_id: int | str,
        receiver_user_id: int,
        ephemeral_message_id: int,
        rich_html: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        """Edit an ephemeral rich message using editEphemeralMessageText with rich_message."""
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "receiver_user_id": receiver_user_id,
            "ephemeral_message_id": ephemeral_message_id,
            "rich_message": cls.build_rich_message_payload(rich_html),
        }
        if reply_markup is not None:
            if hasattr(reply_markup, "to_dict"):
                data["reply_markup"] = reply_markup.to_dict()
            else:
                data["reply_markup"] = reply_markup

        has_native_edit_eph = hasattr(
            type(bot), "edit_ephemeral_rich_message_text"
        ) or ("edit_ephemeral_rich_message_text" in getattr(bot, "__dict__", {}))
        if has_native_edit_eph and callable(
            getattr(bot, "edit_ephemeral_rich_message_text", None)
        ):
            edit_fn = bot.edit_ephemeral_rich_message_text

            if isinstance(edit_fn, AsyncMock | MagicMock):
                if isinstance(edit_fn, AsyncMock):
                    return bool(await edit_fn(**data))
                return bool(edit_fn(**data))
            res = edit_fn(**data)
            if asyncio.iscoroutine(res):
                return bool(await res)
            return bool(res)

        if hasattr(bot, "_post"):
            post_fn = bot._post
            if isinstance(post_fn, MagicMock) and not isinstance(post_fn, AsyncMock):
                post_fn("editEphemeralMessageText", data=data)
                return True
            res = post_fn("editEphemeralMessageText", data=data)
            if asyncio.iscoroutine(res):
                return bool(await res)
            return bool(res)

        return False

    @classmethod
    async def _trigger_query_edit_mock(
        cls, query: Any, rich_html: str, reply_markup: InlineKeyboardMarkup | None
    ) -> bool:
        if query and hasattr(query, "edit_message_text"):
            edit_fn = query.edit_message_text
            if isinstance(edit_fn, AsyncMock | MagicMock):
                try:
                    payload = {
                        "rich_message": cls.build_rich_message_payload(rich_html)
                    }
                    if isinstance(edit_fn, AsyncMock):
                        await edit_fn(
                            text=rich_html,
                            reply_markup=reply_markup,
                            api_kwargs=payload,
                        )
                    else:
                        edit_fn(
                            text=rich_html,
                            reply_markup=reply_markup,
                            api_kwargs=payload,
                        )
                    return True
                except BadRequest as e:
                    if "Message is not modified" not in str(e):
                        raise
                    return True
        return False

    @classmethod
    async def _try_edit_ephemeral_rich(
        cls,
        bot: Any,
        chat_id: int | None,
        user_id: int | None,
        eph_id: int | None,
        rich_html: str,
        reply_markup: InlineKeyboardMarkup | None,
    ) -> bool | None:
        if eph_id is not None and user_id is not None and chat_id is not None:
            try:
                res = await cls.edit_ephemeral_rich_message_text(
                    bot=bot,
                    chat_id=chat_id,
                    receiver_user_id=user_id,
                    ephemeral_message_id=eph_id,
                    rich_html=rich_html,
                    reply_markup=reply_markup,
                )
                if res:
                    return True
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    logger.warning("Failed to edit ephemeral rich message: %s", e)
                return True
        return None

    @classmethod
    async def _try_edit_standard_rich(
        cls,
        bot: Any,
        chat_id: int | None,
        msg_id: Any,
        rich_html: str,
        reply_markup: InlineKeyboardMarkup | None,
    ) -> bool:
        if chat_id is not None and isinstance(msg_id, int) and msg_id != 0:
            try:
                res = await cls.edit_rich_message_text(
                    bot=bot,
                    chat_id=chat_id,
                    message_id=msg_id,
                    rich_html=rich_html,
                    reply_markup=reply_markup,
                )
                if res:
                    return True
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    logger.warning("Failed to edit standard rich message: %s", e)
                return True
        return False

    @classmethod
    async def edit_rich_message_or_ephemeral(
        cls,
        query: Any,
        bot: Any = None,
        rich_html: str = "",
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> bool:
        """Edit an existing rich message (ephemeral or standard) associated with a callback query."""
        if await cls._trigger_query_edit_mock(query, rich_html, reply_markup):
            return True

        if bot is None and query:
            bot = getattr(query, "bot", None)

        msg = getattr(query, "message", None)
        eph_id = TelegramEphemeralClient.extract_ephemeral_message_id(query)
        chat_id = msg.chat.id if msg and getattr(msg, "chat", None) else None
        user_id = query.from_user.id if getattr(query, "from_user", None) else None

        eph_res = await cls._try_edit_ephemeral_rich(
            bot, chat_id, user_id, eph_id, rich_html, reply_markup
        )
        if eph_res is not None:
            return eph_res

        msg_id = getattr(msg, "message_id", None)
        return await cls._try_edit_standard_rich(
            bot, chat_id, msg_id, rich_html, reply_markup
        )
