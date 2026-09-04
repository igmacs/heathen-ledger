import os
import sys
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

# Add project src to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.voice import (
    VoiceInterpreter,
    VoiceInterpretation,
    GeminiVoiceInterpreter,
    get_voice_interpreter,
)


class DummyVoiceInterpreter(VoiceInterpreter):
    """Concrete test implementation of VoiceInterpreter."""

    async def transcribe(self, audio_data: bytes, mime_type: str = "audio/ogg") -> str:
        return "transcribed text"

    async def interpret(
        self,
        audio_data: bytes,
        group_members: list[str] | None = None,
        mime_type: str = "audio/ogg",
    ) -> VoiceInterpretation:
        return VoiceInterpretation(
            transcription="transcribed text",
            command="/pay 10 for coffee",
            raw_response="raw text",
        )


class TestVoiceInterpreter(unittest.IsolatedAsyncioTestCase):
    async def test_dummy_implementation(self):
        interpreter = DummyVoiceInterpreter()
        transcription = await interpreter.transcribe(b"dummy audio")
        self.assertEqual(transcription, "transcribed text")

        interpretation = await interpreter.interpret(
            b"dummy audio", group_members=["Alice"]
        )
        self.assertEqual(interpretation.transcription, "transcribed text")
        self.assertEqual(interpretation.command, "/pay 10 for coffee")
        self.assertEqual(interpretation.raw_response, "raw text")

    def test_interpretation_dataclass_defaults(self):
        result = VoiceInterpretation(transcription="hello world")
        self.assertEqual(result.transcription, "hello world")
        self.assertIsNone(result.command)
        self.assertIsNone(result.raw_response)

    def test_gemini_interpreter_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                GeminiVoiceInterpreter(api_key=None)
            self.assertIn("GEMINI_API_KEY", str(ctx.exception))

    @patch("heathen_ledger.voice.gemini.genai.Client")
    def test_gemini_interpreter_with_explicit_api_key(self, mock_client_cls):
        interpreter = GeminiVoiceInterpreter(api_key="test-api-key")
        mock_client_cls.assert_called_once_with(api_key="test-api-key")
        self.assertEqual(interpreter.api_key, "test-api-key")

    @patch("heathen_ledger.voice.gemini.genai.Client")
    def test_gemini_interpreter_with_env_api_key(self, mock_client_cls):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-api-key"}, clear=True):
            interpreter = GeminiVoiceInterpreter()
            mock_client_cls.assert_called_once_with(api_key="env-api-key")
            self.assertEqual(interpreter.api_key, "env-api-key")

    @patch("heathen_ledger.voice.gemini.genai.Client")
    def test_get_voice_interpreter_factory(self, mock_client_cls):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key"}, clear=True):
            interpreter = get_voice_interpreter(provider="gemini")
            self.assertIsInstance(interpreter, GeminiVoiceInterpreter)

    def test_get_voice_interpreter_unsupported_provider(self):
        with self.assertRaises(ValueError) as ctx:
            get_voice_interpreter(provider="unsupported_provider")
        self.assertIn("Unsupported voice provider", str(ctx.exception))

    @patch("heathen_ledger.voice.gemini.genai.Client")
    async def test_gemini_transcribe(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock(text="Alice paid 25 for dinner")
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        interpreter = GeminiVoiceInterpreter(api_key="test-key")
        result = await interpreter.transcribe(b"fake_audio_bytes")

        self.assertEqual(result, "Alice paid 25 for dinner")
        mock_client.aio.models.generate_content.assert_awaited_once()

    @patch("heathen_ledger.voice.gemini.genai.Client")
    async def test_gemini_interpret_with_command(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        json_output = '{"transcription": "Alice paid 25 for dinner", "command": "/pay @Alice 25 for dinner"}'
        mock_response = MagicMock(text=json_output)
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        interpreter = GeminiVoiceInterpreter(api_key="test-key")
        interpretation = await interpreter.interpret(
            b"fake_audio_bytes", group_members=["@Alice", "@Bob"]
        )

        self.assertEqual(interpretation.transcription, "Alice paid 25 for dinner")
        self.assertEqual(interpretation.command, "/pay @Alice 25 for dinner")
        self.assertEqual(interpretation.raw_response, json_output)

    @patch("heathen_ledger.voice.gemini.genai.Client")
    async def test_gemini_interpret_command_missing_leading_slash(
        self, mock_client_cls
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        json_output = '{"transcription": "settle up", "command": "settle"}'
        mock_response = MagicMock(text=json_output)
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        interpreter = GeminiVoiceInterpreter(api_key="test-key")
        interpretation = await interpreter.interpret(b"fake_audio_bytes")

        self.assertEqual(interpretation.transcription, "settle up")
        self.assertEqual(interpretation.command, "/settle")

    @patch("heathen_ledger.voice.gemini.genai.Client")
    async def test_gemini_interpret_no_command(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        json_output = '{"transcription": "How is everyone doing?", "command": null}'
        mock_response = MagicMock(text=json_output)
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        interpreter = GeminiVoiceInterpreter(api_key="test-key")
        interpretation = await interpreter.interpret(b"fake_audio_bytes")

        self.assertEqual(interpretation.transcription, "How is everyone doing?")
        self.assertIsNone(interpretation.command)

    @patch("heathen_ledger.voice.gemini.genai.Client")
    async def test_gemini_interpret_malformed_json_fallback(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_response = MagicMock(text="Raw non-json text from model")
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        interpreter = GeminiVoiceInterpreter(api_key="test-key")
        interpretation = await interpreter.interpret(b"fake_audio_bytes")

        self.assertEqual(interpretation.transcription, "Raw non-json text from model")
        self.assertIsNone(interpretation.command)


if __name__ == "__main__":
    unittest.main()
