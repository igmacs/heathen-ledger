"""Voice transcription and interpretation package."""

from typing import Optional
from .base import VoiceInterpreter, VoiceInterpretation
from .gemini import GeminiVoiceInterpreter
from .pending_store import PendingVoiceCommand, PendingVoiceCommandStore
from .audio_downloader import VoiceAudioDownloader


def get_voice_interpreter(
    provider: str = "gemini",
    api_key: Optional[str] = None,
) -> VoiceInterpreter:
    """Factory function to get a VoiceInterpreter instance for the configured provider."""
    if provider.lower() == "gemini":
        return GeminiVoiceInterpreter(api_key=api_key)
    raise ValueError(f"Unsupported voice provider: '{provider}'")


__all__ = [
    "VoiceInterpreter",
    "VoiceInterpretation",
    "GeminiVoiceInterpreter",
    "get_voice_interpreter",
    "PendingVoiceCommand",
    "PendingVoiceCommandStore",
    "VoiceAudioDownloader",
]
