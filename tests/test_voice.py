import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project src to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.handlers.expense import pay_command
from heathen_ledger.handlers.voice import (
    clear_pending_voice_commands,
    get_pending_voice_command,
    store_pending_voice_command,
    voice_callback_handler,
    voice_command_handler,
    voice_mention_handler,
    voice_message_handler,
)
from heathen_ledger.models import Expense, Payment
from heathen_ledger.voice import VoiceInterpretation
from telegram.constants import ChatType

from tests.base import BaseDatabaseTestCase


class TestVoiceMessageHandler(unittest.IsolatedAsyncioTestCase):
    def _create_update(self, is_group: bool = True, chat_id: int = -10012345):
        update = MagicMock()
        update.effective_chat.type = ChatType.GROUP if is_group else ChatType.PRIVATE
        update.effective_chat.id = chat_id
        return update

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
        reply_markup = update.message.reply_text.call_args[1].get("reply_markup")
        self.assertIsNotNone(reply_markup)
        self.assertEqual(len(reply_markup.inline_keyboard[0]), 2)
        confirm_btn, reject_btn = reply_markup.inline_keyboard[0]
        self.assertIn("Confirm", confirm_btn.text)
        self.assertTrue(confirm_btn.callback_data.startswith("voice:confirm:"))
        self.assertIn("Reject", reject_btn.text)
        self.assertTrue(reject_btn.callback_data.startswith("voice:reject:"))

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

    async def test_voice_command_no_reply(self):
        update = self._create_update()
        context = MagicMock()
        update.message.reply_to_message = None
        update.message.reply_text = AsyncMock()

        await voice_command_handler(update, context)

        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("reply to an audio or voice message", reply)

    async def test_voice_command_reply_to_non_audio(self):
        update = self._create_update()
        context = MagicMock()
        reply_to = MagicMock()
        reply_to.voice = None
        reply_to.audio = None
        update.message.reply_to_message = reply_to
        update.message.reply_text = AsyncMock()

        await voice_command_handler(update, context)

        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("does not contain a voice note", reply)

    @patch("heathen_ledger.handlers.common.send_response")
    async def test_voice_command_in_private_chat_blocked(self, mock_send_response):
        update = self._create_update(is_group=False)
        context = MagicMock()

        await voice_command_handler(update, context)

        mock_send_response.assert_awaited_once()
        warning = mock_send_response.call_args[0][2]
        self.assertIn("can only be used in a group chat", warning)

    @patch("heathen_ledger.handlers.voice.crud.get_group_by_telegram_id")
    @patch("heathen_ledger.handlers.voice.get_voice_interpreter")
    async def test_voice_command_reply_to_voice_success(
        self, mock_get_interpreter, mock_get_group
    ):
        mock_interpreter = MagicMock()
        mock_interpreter.interpret = AsyncMock(
            return_value=VoiceInterpretation(
                transcription="Bob paid 15 for coffee",
                command="/pay @Bob 15 for coffee",
            )
        )
        mock_get_interpreter.return_value = mock_interpreter
        mock_get_group.return_value = None

        update = self._create_update(chat_id=-10012345)
        context = MagicMock()
        reply_to = MagicMock()
        reply_to.voice = MagicMock(file_id="voice_rep", mime_type="audio/ogg")
        reply_to.audio = None
        update.message.reply_to_message = reply_to
        update.message.reply_text = AsyncMock()

        mock_file = MagicMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"bytes"))
        context.bot.get_file = AsyncMock(return_value=mock_file)

        await voice_command_handler(update, context)

        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("Bob paid 15 for coffee", reply)
        self.assertIn("/pay @Bob 15 for coffee", reply)

    @patch("heathen_ledger.handlers.voice.crud.get_group_by_telegram_id")
    @patch("heathen_ledger.handlers.voice.get_voice_interpreter")
    async def test_voice_mention_handler_bot_tagged(
        self, mock_get_interpreter, mock_get_group
    ):
        mock_interpreter = MagicMock()
        mock_interpreter.interpret = AsyncMock(
            return_value=VoiceInterpretation(
                transcription="Paid 30 for groceries",
                command="/pay 30 for groceries",
            )
        )
        mock_get_interpreter.return_value = mock_interpreter
        mock_get_group.return_value = None

        update = MagicMock()
        context = MagicMock()
        context.bot.username = "HeathenLedgerBot"
        update.effective_chat.id = -10012345
        update.message.text = "@HeathenLedgerBot log this"
        update.message.entities = []

        reply_to = MagicMock()
        reply_to.voice = MagicMock(file_id="voice_tag", mime_type="audio/ogg")
        reply_to.audio = None
        update.message.reply_to_message = reply_to
        update.message.reply_text = AsyncMock()

        mock_file = MagicMock()
        mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"bytes"))
        context.bot.get_file = AsyncMock(return_value=mock_file)

        await voice_mention_handler(update, context)

        update.message.reply_text.assert_awaited_once()
        reply = update.message.reply_text.call_args[0][0]
        self.assertIn("Paid 30 for groceries", reply)
        self.assertIn("/pay 30 for groceries", reply)

    async def test_voice_mention_handler_other_user_tagged_ignored(self):
        update = MagicMock()
        context = MagicMock()
        context.bot.username = "HeathenLedgerBot"
        update.message.text = "@Alice check this out"
        update.message.entities = []

        reply_to = MagicMock()
        reply_to.voice = MagicMock(file_id="voice_tag")
        update.message.reply_to_message = reply_to
        update.message.reply_text = AsyncMock()

        await voice_mention_handler(update, context)

        update.message.reply_text.assert_not_awaited()

    async def test_voice_mention_handler_no_reply_or_non_audio(self):
        context = MagicMock()

        # No reply
        update1 = MagicMock()
        update1.message.reply_to_message = None
        update1.message.reply_text = AsyncMock()
        await voice_mention_handler(update1, context)
        update1.message.reply_text.assert_not_awaited()

        # Reply to non-audio
        update2 = MagicMock()
        reply_to = MagicMock()
        reply_to.voice = None
        reply_to.audio = None
        update2.message.reply_to_message = reply_to
        update2.message.reply_text = AsyncMock()
        await voice_mention_handler(update2, context)
        update2.message.reply_text.assert_not_awaited()

    @patch(
        "heathen_ledger.handlers.expense.process_voice_audio", new_callable=AsyncMock
    )
    async def test_pay_command_reply_to_voice_delegated(self, mock_process_voice):
        update = self._create_update(chat_id=-10012345)
        context = MagicMock()
        context.bot.username = "HeathenLedgerBot"
        update.message.text = "/pay"

        reply_to = MagicMock()
        reply_to.voice = MagicMock(file_id="voice_rep")
        reply_to.audio = None
        update.message.reply_to_message = reply_to

        await pay_command(update, context)

        mock_process_voice.assert_awaited_once()
        kwargs = mock_process_voice.call_args[1]
        self.assertEqual(kwargs["media_message"], reply_to)
        self.assertEqual(kwargs["response_message"], update.message)

    @patch(
        "heathen_ledger.handlers.expense.process_voice_audio", new_callable=AsyncMock
    )
    async def test_pay_command_reply_to_voice_with_explicit_args_not_delegated(
        self, mock_process_voice
    ):
        update = self._create_update(chat_id=-10012345)
        context = MagicMock()
        context.bot.username = "HeathenLedgerBot"
        update.message.text = "/pay 20 for dinner"

        reply_to = MagicMock()
        reply_to.voice = MagicMock(file_id="voice_rep")
        reply_to.audio = None
        update.message.reply_to_message = reply_to

        with patch(
            "heathen_ledger.handlers.expense.parse_pay_message",
            return_value={"error": "test"},
        ):
            update.message.reply_text = AsyncMock()
            await pay_command(update, context)

        mock_process_voice.assert_not_awaited()


class TestVoiceConfirmationCallbacks(BaseDatabaseTestCase):
    def setUp(self):
        super().setUp()
        clear_pending_voice_commands()

    def tearDown(self):
        clear_pending_voice_commands()
        super().tearDown()

    def test_reject_callback_success(self):
        token = store_pending_voice_command(
            command="/pay 25 for dinner",
            creator_id=self.alice.telegram_id,
            creator_username="alice",
            creator_first_name="Alice",
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="I paid 25 for dinner",
        )

        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"voice:reject:{token}",
            chat_id=self.group.telegram_chat_id,
        )
        context = MagicMock()

        asyncio.run(voice_callback_handler(update, context))

        # Query answered with rejection
        update.callback_query.answer.assert_awaited_once_with(text="Command rejected.")
        # Message edited to show Rejected and remove buttons
        update.callback_query.edit_message_text.assert_awaited_once()
        kwargs = update.callback_query.edit_message_text.call_args.kwargs
        self.assertIn("❌ *Rejected*", kwargs["text"])
        self.assertIsNone(kwargs["reply_markup"])
        # Pending command popped
        self.assertIsNone(get_pending_voice_command(token))
        # No expenses created
        expenses = self.session.query(Expense).all()
        self.assertEqual(len(expenses), 0)

    def test_reject_callback_unauthorized(self):
        token = store_pending_voice_command(
            command="/pay 25 for dinner",
            creator_id=self.alice.telegram_id,
            creator_username="alice",
            creator_first_name="Alice",
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="I paid 25 for dinner",
        )

        # Bob tries to reject Alice's voice command
        update = self.create_mock_update(
            telegram_user_id=self.bob.telegram_id,
            callback_data=f"voice:reject:{token}",
            chat_id=self.group.telegram_chat_id,
        )
        context = MagicMock()

        asyncio.run(voice_callback_handler(update, context))

        update.callback_query.answer.assert_awaited_once()
        answer_kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(answer_kwargs.get("show_alert"))
        self.assertIn(
            "Only the person who sent or requested", answer_kwargs.get("text")
        )
        update.callback_query.edit_message_text.assert_not_awaited()
        # Pending command remains in store
        self.assertIsNotNone(get_pending_voice_command(token))

    def test_confirm_pay_command_success(self):
        token = store_pending_voice_command(
            command="/pay 30 for pizza",
            creator_id=self.alice.telegram_id,
            creator_username="alice",
            creator_first_name="Alice",
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="I paid 30 for pizza",
        )

        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"voice:confirm:{token}",
            chat_id=self.group.telegram_chat_id,
        )
        context = MagicMock()

        asyncio.run(voice_callback_handler(update, context))

        # Status message updated
        update.callback_query.edit_message_text.assert_awaited_once()
        kwargs = update.callback_query.edit_message_text.call_args.kwargs
        self.assertIn("Confirmed and executed", kwargs["text"])
        self.assertIsNone(kwargs["reply_markup"])

        # Result message replied in chat
        update.callback_query.message.reply_text.assert_awaited_once()
        reply_call = update.callback_query.message.reply_text.call_args
        reply_text = reply_call.kwargs.get("text") or reply_call.args[0]
        self.assertIn("Recorded expense", reply_text)
        self.assertIn("pizza", reply_text)
        self.assertIn("$30.00", reply_text)
        reply_markup = reply_call.kwargs.get("reply_markup")
        self.assertIsNotNone(reply_markup)

        # Database record created
        expense = (
            self.session.query(Expense).filter(Expense.description == "pizza").first()
        )
        self.assertIsNotNone(expense)
        self.assertEqual(expense.amount, 3000)
        self.assertEqual(expense.payer_id, self.alice.id)
        self.assertEqual(len(expense.splits), 3)

    def test_confirm_payback_command_success(self):
        token = store_pending_voice_command(
            command="/payback @bob 15",
            creator_id=self.alice.telegram_id,
            creator_username="alice",
            creator_first_name="Alice",
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="I paid Bob 15",
        )

        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"voice:confirm:{token}",
            chat_id=self.group.telegram_chat_id,
        )
        context = MagicMock()

        asyncio.run(voice_callback_handler(update, context))

        # Payment created in database
        payment = self.session.query(Payment).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.amount, 1500)
        self.assertEqual(payment.payer_id, self.alice.id)
        self.assertEqual(payment.payee_id, self.bob.id)

        update.callback_query.message.reply_text.assert_awaited_once()
        reply_call = update.callback_query.message.reply_text.call_args
        reply_text = reply_call.kwargs.get("text") or reply_call.args[0]
        self.assertIn("Recorded payment", reply_text)

    def test_confirm_balances_settle_and_history(self):
        # 1. Balances
        token_bal = store_pending_voice_command(
            command="/balances",
            creator_id=self.alice.telegram_id,
            creator_username="alice",
            creator_first_name="Alice",
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="show balances",
        )
        update_bal = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"voice:confirm:{token_bal}",
            chat_id=self.group.telegram_chat_id,
        )
        asyncio.run(voice_callback_handler(update_bal, MagicMock()))
        update_bal.callback_query.message.reply_text.assert_awaited_once()
        bal_text = update_bal.callback_query.message.reply_text.call_args.kwargs.get(
            "text"
        )
        self.assertIn("Balances", bal_text)

        # 2. Settle
        token_set = store_pending_voice_command(
            command="/settle",
            creator_id=self.alice.telegram_id,
            creator_username="alice",
            creator_first_name="Alice",
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="settle up",
        )
        update_set = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"voice:confirm:{token_set}",
            chat_id=self.group.telegram_chat_id,
        )
        asyncio.run(voice_callback_handler(update_set, MagicMock()))
        update_set.callback_query.message.reply_text.assert_awaited_once()
        set_text = update_set.callback_query.message.reply_text.call_args.kwargs.get(
            "text"
        )
        self.assertTrue("Settlement Plan" in set_text or "settled up" in set_text)

        # 3. History
        token_hist = store_pending_voice_command(
            command="/history",
            creator_id=self.alice.telegram_id,
            creator_username="alice",
            creator_first_name="Alice",
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="view history",
        )
        update_hist = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"voice:confirm:{token_hist}",
            chat_id=self.group.telegram_chat_id,
        )
        asyncio.run(voice_callback_handler(update_hist, MagicMock()))
        update_hist.callback_query.message.reply_text.assert_awaited_once()

    def test_confirm_unauthorized_user(self):
        token = store_pending_voice_command(
            command="/pay 10 for coffee",
            creator_id=self.alice.telegram_id,
            creator_username="alice",
            creator_first_name="Alice",
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="I paid 10 for coffee",
        )

        update = self.create_mock_update(
            telegram_user_id=self.bob.telegram_id,
            callback_data=f"voice:confirm:{token}",
            chat_id=self.group.telegram_chat_id,
        )
        context = MagicMock()

        asyncio.run(voice_callback_handler(update, context))

        update.callback_query.answer.assert_awaited_once()
        answer_kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(answer_kwargs.get("show_alert"))
        self.assertIn(
            "Only the person who sent or requested", answer_kwargs.get("text")
        )
        self.assertEqual(len(self.session.query(Expense).all()), 0)

    def test_expired_or_already_processed_callback(self):
        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data="voice:confirm:nonexistent_token",
            chat_id=self.group.telegram_chat_id,
        )
        context = MagicMock()

        asyncio.run(voice_callback_handler(update, context))

        update.callback_query.answer.assert_awaited_once()
        answer_kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(answer_kwargs.get("show_alert"))
        self.assertIn("expired or was already processed", answer_kwargs.get("text"))

    def test_confirm_pay_with_unknown_user_error(self):
        token = store_pending_voice_command(
            command="/pay 20 split @unknown_user",
            creator_id=self.alice.telegram_id,
            creator_username="alice",
            creator_first_name="Alice",
            authorized_user_ids={self.alice.telegram_id},
            chat_id=self.group.telegram_chat_id,
            transcription="pay 20 split unknown",
        )

        update = self.create_mock_update(
            telegram_user_id=self.alice.telegram_id,
            callback_data=f"voice:confirm:{token}",
            chat_id=self.group.telegram_chat_id,
        )
        context = MagicMock()

        asyncio.run(voice_callback_handler(update, context))

        update.callback_query.message.reply_text.assert_awaited_once()
        reply_text = update.callback_query.message.reply_text.call_args.kwargs.get(
            "text"
        )
        self.assertIn("@unknown_user", reply_text)
        self.assertEqual(len(self.session.query(Expense).all()), 0)


if __name__ == "__main__":
    unittest.main()
