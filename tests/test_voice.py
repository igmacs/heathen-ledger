import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project src to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.handlers.voice import voice_message_handler
from heathen_ledger.voice import VoiceInterpretation


class TestVoiceMessageHandler(unittest.IsolatedAsyncioTestCase):
    async def test_no_message_or_audio(self):
        context = MagicMock()

        # None message
        update = MagicMock()
        update.message = None
        await voice_message_handler(update, context)

        # Neither voice nor audio
        update2 = MagicMock()
        update2.message.voice = None
        update2.message.audio = None
        await voice_message_handler(update2, context)

    @patch("heathen_ledger.handlers.voice.get_voice_interpreter")
    async def test_missing_api_key_notification(self, mock_get_interpreter):
        mock_get_interpreter.side_effect = ValueError("No API key provided")
        update = MagicMock()
        context = MagicMock()
        update.message.voice = MagicMock(file_id="voice_123")
        update.message.audio = None
        update.message.reply_text = AsyncMock()

        await voice_message_handler(update, context)

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        self.assertIn("GEMINI_API_KEY", text)
        self.assertIn("not configured", text)

    @patch("heathen_ledger.handlers.voice.crud.get_group_by_telegram_id")
    @patch("heathen_ledger.handlers.voice.get_voice_interpreter")
    async def test_successful_interpretation_with_command(
        self, mock_get_interpreter, mock_get_group
    ):
        mock_interpreter = MagicMock()
        mock_interpreter.interpret = AsyncMock(
            return_value=VoiceInterpretation(
                transcription="Alice paid 25 for dinner",
                command="/pay @Alice 25 for dinner",
            )
        )
        mock_get_interpreter.return_value = mock_interpreter

        member1 = MagicMock(username="Alice", first_name="Alice")
        member2 = MagicMock(username=None, first_name="Bob")
        mock_group = MagicMock(members=[member1, member2])
        mock_get_group.return_value = mock_group

        update = MagicMock()
        context = MagicMock()
        update.effective_chat.id = -10012345
        update.message.voice = MagicMock(file_id="voice_123", mime_type="audio/ogg")
        update.message.audio = None
        update.message.reply_text = AsyncMock()

        mock_file = MagicMock()
        mock_file.download_as_bytearray = AsyncMock(
            return_value=bytearray(b"dummy_bytes")
        )
        context.bot.get_file = AsyncMock(return_value=mock_file)

        await voice_message_handler(update, context)

        context.bot.get_file.assert_awaited_once_with("voice_123")
        mock_interpreter.interpret.assert_awaited_once()
        kwargs = mock_interpreter.interpret.call_args[1]
        self.assertIn("@Alice", kwargs["group_members"])
        self.assertIn("Bob", kwargs["group_members"])

        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("Alice paid 25 for dinner", reply)
        self.assertIn("/pay @Alice 25 for dinner", reply)

    @patch("heathen_ledger.handlers.voice.crud.get_group_by_telegram_id")
    @patch("heathen_ledger.handlers.voice.get_voice_interpreter")
    async def test_successful_interpretation_audio_file_no_command(
        self, mock_get_interpreter, mock_get_group
    ):
        mock_interpreter = MagicMock()
        mock_interpreter.interpret = AsyncMock(
            return_value=VoiceInterpretation(
                transcription="Just chatting here",
                command=None,
            )
        )
        mock_get_interpreter.return_value = mock_interpreter
        mock_get_group.return_value = None

        update = MagicMock()
        context = MagicMock()
        update.effective_chat.id = -10012345
        update.message.voice = None
        update.message.audio = MagicMock(file_id="audio_456", mime_type="audio/mpeg")
        update.message.reply_text = AsyncMock()

        mock_file = MagicMock()
        mock_file.download_as_bytearray = AsyncMock(
            return_value=bytearray(b"audio_bytes")
        )
        context.bot.get_file = AsyncMock(return_value=mock_file)

        await voice_message_handler(update, context)

        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("Just chatting here", reply)
        self.assertIn("No ledger command was recognized", reply)

    @patch("heathen_ledger.handlers.voice.get_voice_interpreter")
    async def test_download_failure(self, mock_get_interpreter):
        mock_get_interpreter.return_value = MagicMock()
        update = MagicMock()
        context = MagicMock()
        update.effective_chat.id = -10012345
        update.message.voice = MagicMock(file_id="voice_bad")
        update.message.audio = None
        update.message.reply_text = AsyncMock()

        context.bot.get_file = AsyncMock(
            side_effect=Exception("Telegram connection timeout")
        )

        await voice_message_handler(update, context)

        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("Failed to download audio", reply)

    @patch("heathen_ledger.handlers.voice.get_voice_interpreter")
    async def test_interpret_failure(self, mock_get_interpreter):
        mock_interpreter = MagicMock()
        mock_interpreter.interpret = AsyncMock(
            side_effect=Exception("Gemini quota exceeded")
        )
        mock_get_interpreter.return_value = mock_interpreter

        update = MagicMock()
        context = MagicMock()
        update.effective_chat.id = -10012345
        update.message.voice = MagicMock(file_id="voice_123")
        update.message.audio = None
        update.message.reply_text = AsyncMock()

        mock_file = MagicMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"bytes"))
        context.bot.get_file = AsyncMock(return_value=mock_file)

        await voice_message_handler(update, context)

        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("Failed to transcribe or interpret audio", reply)


if __name__ == "__main__":
    unittest.main()
