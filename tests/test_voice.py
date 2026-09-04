import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock

# Add project src to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.handlers.voice import voice_message_handler


class TestVoiceMessageHandler(unittest.IsolatedAsyncioTestCase):
    async def test_voice_message_echo(self):
        update = MagicMock()
        context = MagicMock()

        update.message.voice.duration = 4
        update.message.voice.file_size = 2048
        update.message.voice.file_id = "voice_file_123"
        update.message.audio = None
        update.message.reply_voice = AsyncMock()

        await voice_message_handler(update, context)

        update.message.reply_voice.assert_awaited_once()
        args, kwargs = update.message.reply_voice.call_args
        self.assertEqual(kwargs["voice"], "voice_file_123")
        self.assertIn("4s", kwargs["caption"])
        self.assertIn("2048 bytes", kwargs["caption"])

    async def test_audio_message_echo(self):
        update = MagicMock()
        context = MagicMock()

        update.message.voice = None
        update.message.audio.duration = 12
        update.message.audio.file_size = 8192
        update.message.audio.file_id = "audio_file_456"
        update.message.reply_audio = AsyncMock()

        await voice_message_handler(update, context)

        update.message.reply_audio.assert_awaited_once()
        args, kwargs = update.message.reply_audio.call_args
        self.assertEqual(kwargs["audio"], "audio_file_456")
        self.assertIn("12s", kwargs["caption"])
        self.assertIn("8192 bytes", kwargs["caption"])

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
