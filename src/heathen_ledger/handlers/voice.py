import logging
from telegram import Update
from telegram.constants import ChatAction, MessageEntityType
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from .. import crud
from ..voice import get_voice_interpreter

logger = logging.getLogger(__name__)


async def is_bot_mentioned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the bot was mentioned in the update message."""
    if not update.message or not update.message.text:
        return False

    bot_username = getattr(context.bot, "username", None)
    if not bot_username and hasattr(context.bot, "get_me"):
        try:
            bot_user = await context.bot.get_me()
            bot_username = getattr(bot_user, "username", None)
        except Exception:
            bot_username = None

    text = update.message.text
    if bot_username:
        if f"@{bot_username.lower()}" in text.lower():
            return True

    entities = update.message.entities or []
    for entity in entities:
        if entity.type == MessageEntityType.MENTION and bot_username:
            mention = text[entity.offset : entity.offset + entity.length]
            if mention.lstrip("@").lower() == bot_username.lower():
                return True
        elif entity.type == MessageEntityType.TEXT_MENTION and entity.user:
            bot_id = getattr(context.bot, "id", None)
            if bot_id and entity.user.id == bot_id:
                return True

    return False


async def process_voice_audio(
    media_message,
    response_message,
    context: ContextTypes.DEFAULT_TYPE,
    session: Session,
    chat_id: int | None = None,
) -> None:
    """Download, transcribe, and interpret audio/voice from media_message and send response via response_message."""
    media = media_message.voice or media_message.audio
    if not media:
        return

    # Check if a voice interpreter can be instantiated (GEMINI_API_KEY check)
    try:
        interpreter = get_voice_interpreter()
    except ValueError:
        await response_message.reply_text(
            "⚠️ Voice message received, but `GEMINI_API_KEY` is not configured.\n"
            "Please set `GEMINI_API_KEY` in your `.env` to enable voice transcription and command recognition."
        )
        return

    if chat_id is None:
        target_chat = getattr(response_message, "chat", None)
        if target_chat and hasattr(target_chat, "id"):
            chat_id = target_chat.id

    # Indicate typing activity
    if chat_id is not None:
        try:
            await context.bot.send_chat_action(
                chat_id=chat_id,
                action=ChatAction.TYPING,
            )
        except Exception:
            pass

    # Download audio bytes
    try:
        telegram_file = await context.bot.get_file(media.file_id)
        audio_bytes = bytes(await telegram_file.download_as_bytearray())
    except Exception as e:
        logger.exception("Failed to download voice/audio file from Telegram")
        await response_message.reply_text(
            f"❌ Failed to download audio from Telegram: {e}"
        )
        return

    # Gather group members context
    group_members = []
    if chat_id is not None:
        group = crud.get_group_by_telegram_id(session, chat_id)
        if group and group.members:
            for member in group.members:
                if member.username:
                    group_members.append(f"@{member.username}")
                elif member.first_name:
                    group_members.append(member.first_name)

    # Determine MIME type
    mime_type = getattr(media, "mime_type", None) or (
        "audio/ogg" if media_message.voice else "audio/mpeg"
    )

    # Transcribe and interpret
    try:
        interpretation = await interpreter.interpret(
            audio_bytes,
            group_members=group_members,
            mime_type=mime_type,
        )
    except Exception as e:
        logger.exception("Error processing voice message with Gemini")
        await response_message.reply_text(
            f"❌ Failed to transcribe or interpret audio: {e}"
        )
        return

    # Format response
    reply_lines = [f'🎙️ *Transcription:*\n"{interpretation.transcription}"']
    if interpretation.command:
        reply_lines.append(
            f"\n💡 *Interpreted Command:*\n`{interpretation.command}`\n\n"
            "_(Command confirmation buttons will be enabled in Phase 4)_"
        )
    else:
        reply_lines.append("\n❓ _No ledger command was recognized from this message._")

    await response_message.reply_text(
        "\n".join(reply_lines),
        parse_mode="Markdown",
    )


@with_db_session
async def voice_command_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle /voice command: process replied-to voice/audio message."""
    if not update.message:
        return

    reply_to = update.message.reply_to_message
    if not reply_to:
        await update.message.reply_text(
            "💡 To process a voice note, reply to an audio or voice message with `/voice`, `/pay`, or tag the bot.",
            parse_mode="Markdown",
        )
        return

    media = reply_to.voice or reply_to.audio
    if not media:
        await update.message.reply_text(
            "⚠️ The replied message does not contain a voice note or audio file."
        )
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    await process_voice_audio(
        media_message=reply_to,
        response_message=update.message,
        context=context,
        session=session,
        chat_id=chat_id,
    )


@with_db_session
async def voice_mention_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle mentions in replies to voice/audio messages."""
    if not update.message:
        return

    reply_to = update.message.reply_to_message
    if not reply_to:
        return

    media = reply_to.voice or reply_to.audio
    if not media:
        return

    if not await is_bot_mentioned(update, context):
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    await process_voice_audio(
        media_message=reply_to,
        response_message=update.message,
        context=context,
        session=session,
        chat_id=chat_id,
    )


@with_db_session
async def voice_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle incoming voice/audio messages directly (for backwards compatibility/direct calls)."""
    if not update.message:
        return

    media = update.message.voice or update.message.audio
    if not media:
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    await process_voice_audio(
        media_message=update.message,
        response_message=update.message,
        context=context,
        session=session,
        chat_id=chat_id,
    )
