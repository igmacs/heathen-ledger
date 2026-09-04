import os
from typing import Optional, List
from google import genai

from .base import VoiceInterpreter, VoiceInterpretation


class GeminiVoiceInterpreter(VoiceInterpreter):
    """Google Gemini implementation of VoiceInterpreter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No API key provided. Please set the GEMINI_API_KEY environment variable."
            )
        self.model_name = model_name
        self.client = genai.Client(api_key=self.api_key)

    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/ogg") -> str:
        """Transcribe raw audio bytes to text using Gemini.

        To be implemented in Phase 3A.
        """
        raise NotImplementedError("Phase 3A will implement Gemini transcription.")

    async def interpret(
        self,
        audio_data: bytes,
        group_members: Optional[List[str]] = None,
        mime_type: str = "audio/ogg",
    ) -> VoiceInterpretation:
        """Transcribe and interpret audio bytes to bot command using Gemini.

        To be implemented in Phase 3B.
        """
        raise NotImplementedError(
            "Phase 3B will implement Gemini command interpretation."
        )
