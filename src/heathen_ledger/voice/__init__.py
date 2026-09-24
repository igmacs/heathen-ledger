"""Voice transcription and interpretation package."""

from .audio_downloader import VoiceAudioDownloader
from .base import VoiceInterpretation, VoiceInterpreter
from .gemini import GeminiVoiceInterpreter
from .pending_store import PendingVoiceCommand, PendingVoiceCommandStore


def get_voice_interpreter(
    provider: str = "gemini",
    api_key: str | None = None,
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
