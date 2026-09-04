import logging
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from .. import crud
from ..voice import get_voice_interpreter

logger = logging.getLogger(__name__)


@with_db_session
async def voice_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle incoming voice/audio messages: download, transcribe, and interpret via VoiceInterpreter."""
    if not update.message:
        return

    media = update.message.voice or update.message.audio
    if not media:
        return

    # Check if a voice interpreter can be instantiated (GEMINI_API_KEY check)
    try:
        interpreter = get_voice_interpreter()
    except ValueError:
        await update.message.reply_text(
            "⚠️ Voice message received, but `GEMINI_API_KEY` is not configured.\n"
            "Please set `GEMINI_API_KEY` in your `.env` to enable voice transcription and command recognition."
        )
        return

    # Indicate typing activity
    if update.effective_chat:
        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id,
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
        await update.message.reply_text(
            f"❌ Failed to download audio from Telegram: {e}"
        )
        return

    # Gather group members context
    group_members = []
    if update.effective_chat:
        group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
        if group and group.members:
            for member in group.members:
                if member.username:
                    group_members.append(f"@{member.username}")
                elif member.first_name:
                    group_members.append(member.first_name)

    # Determine MIME type
    mime_type = getattr(media, "mime_type", None) or (
        "audio/ogg" if update.message.voice else "audio/mpeg"
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
        await update.message.reply_text(
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

    await update.message.reply_text(
        "\n".join(reply_lines),
        parse_mode="Markdown",
    )
