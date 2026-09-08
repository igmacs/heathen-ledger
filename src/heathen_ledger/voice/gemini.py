import datetime
import json
import logging
import os
from typing import Optional, List
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .base import VoiceInterpreter, VoiceInterpretation

logger = logging.getLogger(__name__)


class InterpretationResponseSchema(BaseModel):
    transcription: str = Field(
        description="The exact spoken text transcribed from the audio in the original language."
    )
    command: Optional[str] = Field(
        None,
        description="The mapped Telegram bot command starting with / (e.g. '/pay @Alice 25 for dinner') if a command intent was detected, or null if no command was intended.",
    )


class GeminiVoiceInterpreter(VoiceInterpreter):
    """Google Gemini implementation of VoiceInterpreter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No API key provided. Please set the GEMINI_API_KEY environment variable."
            )
        self.model_name = (
            model_name or os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash-lite"
        )
        self.client = genai.Client(api_key=self.api_key)

    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/ogg") -> str:
        """Transcribe raw audio bytes to text using Gemini."""
        prompt = (
            "Please transcribe the spoken words in this audio exactly as spoken in the original language. "
            "Output only the plain transcription, without any preamble or commentary."
        )
        audio_part = types.Part.from_bytes(data=audio_data, mime_type=mime_type)
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[audio_part, prompt],
        )
        return (response.text or "").strip()

    async def interpret(
        self,
        audio_data: bytes,
        group_members: Optional[List[str]] = None,
        mime_type: str = "audio/ogg",
    ) -> VoiceInterpretation:
        """Transcribe and interpret audio bytes to bot command using Gemini."""
        members_desc = (
            ", ".join(group_members) if group_members else "None registered yet"
        )
        today_iso = datetime.date.today().isoformat()
        prompt = (
            "You are an AI assistant for Heathen Ledger, a Telegram expense-sharing bot.\n"
            f"Today's date is: {today_iso}\n\n"
            "Your tasks:\n"
            "1. Transcribe the spoken audio message accurately in its original language.\n"
            "2. Determine if the speaker intends to invoke one of the supported bot commands:\n"
            "   - /pay: Record an expense.\n"
            "     Syntax: /pay <amount> [for <description>] [by <payer_spec>] [split <split_spec>] [on <date>]\n"
            "     Examples:\n"
            "       'I paid 25 for lunch' -> /pay 25 for lunch\n"
            "       'Alice paid 50 for groceries' -> /pay 50 for groceries by @Alice\n"
            "       'Dinner was 90, paid with Bob from our joint account' -> /pay 90 for Dinner by me @Bob\n"
            "       'We got pizza for 40, I paid 25 and Charlie paid 15' -> /pay 40 for pizza by me:25 @Charlie:15\n"
            "       'I paid 60 for escape room for Alice and Bob only' -> /pay 60 for escape room split @Alice @Bob\n"
            "       'Bought drinks for 30, Bob owes 10 and Charlie owes 20' -> /pay 30 for drinks split @Bob:10 @Charlie:20\n"
            "       'I paid 45 for groceries for everyone except Dave' -> /pay 45 for groceries split except @Dave\n"
            "       'Alice paid 50 for dinner yesterday' -> /pay 50 for dinner by @Alice on <date_of_yesterday>\n"
            "   - /payback: Record a direct settlement payment.\n"
            "     Syntax: /payback [payer] <recipient> <amount>\n"
            "     Examples:\n"
            "       'I paid Alice 15' -> /payback @Alice 15\n"
            "       'Bob paid Alice 20' -> /payback @Bob @Alice 20\n"
            "   - /balances: View balances.\n"
            "   - /settle: Settle debts.\n"
            "   - /history: View transaction history.\n\n"
            f"Known group members: {members_desc}\n\n"
            "Guidelines:\n"
            "- If a mentioned person corresponds to a known group member, use their username prefixed with '@' (e.g. @Alice).\n"
            "- If the speaker refers to themselves paying or participating, use 'me' in 'by' or 'split'.\n"
            "- If the speaker mentions a date (e.g. yesterday, on Monday), resolve it to ISO format YYYY-MM-DD in the 'on' clause.\n"
            "- Amounts must be positive decimal numbers.\n"
            "- If the user did NOT intend to issue a bot command, set command to null.\n"
        )

        audio_part = types.Part.from_bytes(data=audio_data, mime_type=mime_type)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=InterpretationResponseSchema,
        )

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[audio_part, prompt],
            config=config,
        )

        raw_text = (response.text or "").strip()
        try:
            data = json.loads(raw_text)
            transcription = data.get("transcription", "").strip()
            command = data.get("command")
            if command:
                command = command.strip()
                if not command.startswith("/"):
                    command = f"/{command}"
            return VoiceInterpretation(
                transcription=transcription,
                command=command,
                raw_response=raw_text,
            )
        except Exception as e:
            logger.warning(f"Failed to parse structured JSON from Gemini response: {e}")
            return VoiceInterpretation(
                transcription=raw_text,
                command=None,
                raw_response=raw_text,
            )
