import logging

logger = logging.getLogger(__name__)


class VoiceAudioDownloader:
    """Downloads audio bytes from Telegram and detects mime types."""

    @classmethod
    async def download(cls, bot, media_message) -> tuple[bytes, str]:
        """Downloads voice or audio file bytes and returns (audio_bytes, mime_type)."""
        media = media_message.voice or media_message.audio
        if not media:
            raise ValueError("Message does not contain voice or audio media.")

        telegram_file = await bot.get_file(media.file_id)
        audio_bytes = bytes(await telegram_file.download_as_bytearray())

        mime_type = getattr(media, "mime_type", None) or (
            "audio/ogg" if media_message.voice else "audio/mpeg"
        )
        return audio_bytes, mime_type
