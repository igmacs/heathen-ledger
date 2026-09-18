import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class ReceiptImageDownloader:
    """Downloads image bytes from Telegram photo or image document."""

    @classmethod
    async def download(cls, bot, media_message) -> Tuple[bytes, str]:
        """Downloads image file bytes and returns (image_bytes, mime_type)."""
        file_id = None
        mime_type = "image/jpeg"

        if getattr(media_message, "photo", None):
            # Telegram provides photo sizes from smallest to largest; the last is highest resolution
            photo_size = media_message.photo[-1]
            file_id = photo_size.file_id
            mime_type = "image/jpeg"
        elif getattr(media_message, "document", None):
            doc = media_message.document
            doc_mime = getattr(doc, "mime_type", "") or ""
            if doc_mime.startswith("image/"):
                file_id = doc.file_id
                mime_type = doc_mime
            else:
                raise ValueError(
                    f"Document has unsupported MIME type '{doc_mime}'. Expected an image."
                )
        else:
            raise ValueError("Message does not contain photo or image document.")

        telegram_file = await bot.get_file(file_id)
        image_bytes = bytes(await telegram_file.download_as_bytearray())
        return image_bytes, mime_type
