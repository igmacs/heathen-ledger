from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class VoiceInterpretation:
    """Represents the interpreted result of a voice message."""

    transcription: str
    command: Optional[str] = None
    raw_response: Optional[str] = None


class VoiceInterpreter(ABC):
    """Abstract base class defining the interface for voice transcription and interpretation."""

    @abstractmethod
    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/ogg") -> str:
        """Transcribe raw audio bytes into plain text.

        Args:
            audio_data: Raw bytes of the audio file.
            mime_type: MIME type of the audio (default: audio/ogg for Telegram voice notes).

        Returns:
            Transcribed text.
        """
        pass

    @abstractmethod
    async def interpret(
        self,
        audio_data: bytes,
        group_members: Optional[List[str]] = None,
        mime_type: str = "audio/ogg",
    ) -> VoiceInterpretation:
        """Transcribe and interpret audio bytes into an intent/bot command.

        Args:
            audio_data: Raw bytes of the audio file.
            group_members: Optional list of known group member usernames.
            mime_type: MIME type of the audio.

        Returns:
            VoiceInterpretation containing the raw transcription and proposed command.
        """
        pass
