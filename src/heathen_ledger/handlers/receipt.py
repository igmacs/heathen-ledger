"""Handlers for scanning and itemizing receipt/ticket photos."""

import logging
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from .common import send_response
from .voice import is_bot_mentioned
from ..receipt import get_receipt_parser
from ..services import ReceiptService

logger = logging.getLogger(__name__)


def is_image_media(message) -> bool:
    """Check if message contains a photo or image document."""
    if not message:
        return False
    if message.photo:
        return True
    if message.document and getattr(message.document, "mime_type", "").startswith(
        "image/"
    ):
        return True
    return False


async def process_receipt_media(
    media_message,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int | None = None,
) -> None:
    """Process receipt image from media_message and send formatted itemization."""
    if not is_image_media(media_message):
        return

    # Check if receipt parser can be instantiated (GEMINI_API_KEY check)
    try:
        get_receipt_parser()
    except ValueError:
        await send_response(
            update,
            context,
            "⚠️ Receipt photo received, but `GEMINI_API_KEY` is not configured.\n"
            "Please set `GEMINI_API_KEY` in your `.env` to enable receipt OCR scanning.",
        )
        return

    if chat_id is None:
        target_chat = getattr(update, "effective_chat", None)
        if target_chat and hasattr(target_chat, "id"):
            chat_id = target_chat.id

    try:
        _, formatted_text = await ReceiptService.process_receipt_image(
            bot=context.bot,
            media_message=media_message,
            chat_id=chat_id,
        )
        await send_response(
            update,
            context,
            formatted_text,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("Failed to process receipt image with Gemini")
        await send_response(
            update,
            context,
            f"❌ Failed to parse receipt image: {e}",
            parse_mode="Markdown",
        )


async def ticket_command_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /ticket or /receipt command: process captioned photo or replied-to photo."""
    if not update.message:
        return

    # Case 1: The command message itself has a photo (e.g. photo sent with caption /ticket)
    if is_image_media(update.message):
        chat_id = update.effective_chat.id if update.effective_chat else None
        return await process_receipt_media(
            media_message=update.message,
            update=update,
            context=context,
            chat_id=chat_id,
        )

    # Case 2: Replied to a message containing a photo
    reply_to = update.message.reply_to_message
    if reply_to and is_image_media(reply_to):
        chat_id = update.effective_chat.id if update.effective_chat else None
        return await process_receipt_media(
            media_message=reply_to,
            update=update,
            context=context,
            chat_id=chat_id,
        )

    # Case 3: No photo attached or replied to
    await send_response(
        update,
        context,
        "💡 To parse a receipt, reply to a photo with `/ticket` or send a photo with the caption `/ticket`.",
        parse_mode="Markdown",
    )


async def ticket_photo_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle incoming photos: auto-process in private DMs or if caption has command/mention."""
    if not update.message or not is_image_media(update.message):
        return

    chat = update.effective_chat
    is_private = chat is not None and chat.type == ChatType.PRIVATE

    if is_private:
        # In 1-on-1 DM chats, process any photo directly
        chat_id = chat.id if chat else None
        return await process_receipt_media(
            media_message=update.message,
            update=update,
            context=context,
            chat_id=chat_id,
        )

    # In group chats, verify caption mentions bot or uses command
    caption = (update.message.caption or "").strip()
    has_command = caption.lower().startswith(("/ticket", "/receipt"))
    has_mention = await is_bot_mentioned(update, context)

    if has_command or has_mention:
        chat_id = chat.id if chat else None
        return await process_receipt_media(
            media_message=update.message,
            update=update,
            context=context,
            chat_id=chat_id,
        )


async def ticket_mention_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle replies mentioning the bot when replied-to message is an image."""
    if not update.message:
        return

    reply_to = update.message.reply_to_message
    if not reply_to or not is_image_media(reply_to):
        return

    if not await is_bot_mentioned(update, context):
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    await process_receipt_media(
        media_message=reply_to,
        update=update,
        context=context,
        chat_id=chat_id,
    )
