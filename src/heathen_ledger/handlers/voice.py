import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def voice_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle incoming voice/audio messages by echoing them back with metadata."""
    if not update.message:
        return

    voice = update.message.voice
    audio = update.message.audio

    if voice:
        duration = voice.duration
        file_size = voice.file_size or 0
        caption = (
            f"🎙️ Received voice note ({duration}s, {file_size} bytes). Echoing it back!"
        )
        await update.message.reply_voice(
            voice=voice.file_id,
            caption=caption,
        )
    elif audio:
        duration = audio.duration
        file_size = audio.file_size or 0
        caption = (
            f"🎵 Received audio file ({duration}s, {file_size} bytes). Echoing it back!"
        )
        await update.message.reply_audio(
            audio=audio.file_id,
            caption=caption,
        )
