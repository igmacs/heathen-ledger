"""Service layer for voice transcription, interpretation, and pending command lifecycle."""

import contextlib
import logging

from sqlalchemy.orm import Session
from telegram import Bot, InlineKeyboardMarkup, Message
from telegram.constants import ChatAction

from ..formatters import generate_expense_reply_text
from ..keyboards import ExpenseKeyboardBuilder
from ..parser import PayCommandParser
from ..repositories import GroupRepository
from ..voice import (
    PendingVoiceCommand,
    PendingVoiceCommandStore,
    VoiceAudioDownloader,
    VoiceInterpretation,
    get_voice_interpreter,
)
from .exceptions import UserNotFoundError, ValidationError
from .expense_service import ExpenseService
from .registration_service import MemberRegistrationService

logger = logging.getLogger(__name__)


class VoiceService:
    """Service orchestrating voice note downloading, transcription, and command confirmation."""

    _store = PendingVoiceCommandStore()

    @classmethod
    def get_store(cls) -> PendingVoiceCommandStore:
        """Return the backing PendingVoiceCommandStore."""
        return cls._store

    @classmethod
    def store_pending_command(
        cls,
        command: str,
        creator_id: int | None,
        creator_username: str | None,
        creator_first_name: str | None,
        authorized_user_ids: set[int],
        chat_id: int,
        transcription: str,
    ) -> str:
        """Store an unconfirmed voice command and return a short unique token."""
        return cls._store.store(
            command=command,
            creator_id=creator_id,
            creator_username=creator_username,
            creator_first_name=creator_first_name,
            authorized_user_ids=authorized_user_ids,
            chat_id=chat_id,
            transcription=transcription,
        )

    @classmethod
    def get_pending_command(cls, token: str) -> PendingVoiceCommand | None:
        """Retrieve a pending voice command by token."""
        return cls._store.get(token)

    @classmethod
    def pop_pending_command(cls, token: str) -> PendingVoiceCommand | None:
        """Atomically pop a pending voice command by token."""
        return cls._store.pop(token)

    @classmethod
    def clear_pending_commands(cls) -> None:
        """Clear all pending commands."""
        cls._store.clear()

    @classmethod
    def get_group_member_names(cls, session: Session, chat_id: int | None) -> list[str]:
        """Gather group member handles/names for Gemini prompting context."""
        group_members = []
        if chat_id is not None:
            group = GroupRepository(session).get_by_telegram_id(chat_id)
            if group and group.members:
                for member in group.members:
                    if member.username:
                        group_members.append(f"@{member.username}")
                    elif member.first_name:
                        group_members.append(member.first_name)
        return group_members

    @classmethod
    async def process_voice_audio(
        cls,
        bot: Bot,
        media_message: Message,
        session: Session,
        chat_id: int | None = None,
        requester_user_id: int | None = None,
    ) -> tuple[VoiceInterpretation, str | None]:
        """Download, transcribe, interpret, and store pending command for audio message.

        Returns:
            (interpretation: VoiceInterpretation, token: Optional[str])
        """
        media = media_message.voice or media_message.audio
        if not media:
            raise ValidationError("Message does not contain voice or audio.")

        interpreter = get_voice_interpreter()

        if chat_id is not None:
            with contextlib.suppress(Exception):
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        audio_bytes, mime_type = await VoiceAudioDownloader.download(bot, media_message)
        group_members = cls.get_group_member_names(session, chat_id)

        interpretation = await interpreter.interpret(
            audio_bytes, group_members=group_members, mime_type=mime_type
        )

        token = None
        if interpretation.command:
            speaker = getattr(media_message, "from_user", None)
            creator_id = getattr(speaker, "id", None)
            creator_username = getattr(speaker, "username", None)
            creator_first_name = getattr(speaker, "first_name", None)

            authorized_user_ids: set[int] = set()
            if creator_id is not None:
                authorized_user_ids.add(creator_id)
            if requester_user_id is not None:
                authorized_user_ids.add(requester_user_id)

            if chat_id is not None:
                token = cls.store_pending_command(
                    command=interpretation.command,
                    creator_id=creator_id,
                    creator_username=creator_username,
                    creator_first_name=creator_first_name,
                    authorized_user_ids=authorized_user_ids,
                    chat_id=chat_id,
                    transcription=interpretation.transcription,
                )

        return interpretation, token

    @classmethod
    def execute_confirmed_command(
        cls,
        command_str: str,
        chat_id: int,
        creator_id: int,
        creator_username: str | None,
        creator_first_name: str | None,
        session: Session,
        chat_title: str | None = None,
    ) -> tuple[str, InlineKeyboardMarkup | None]:
        cmd_clean = command_str.strip()
        if not cmd_clean.startswith("/"):
            cmd_clean = f"/{cmd_clean}"

        if not cmd_clean.lower().startswith("/pay ") and cmd_clean.lower() != "/pay":
            return f"⚠️ Unsupported command from voice note: `{cmd_clean}`", None

        # Resolve sender and group
        reg_res = MemberRegistrationService.register_user(
            session=session,
            group=chat_id,
            target=creator_id,
            username=creator_username,
            first_name=creator_first_name or f"User{creator_id}",
            chat_title=chat_title,
        )
        sender, group = reg_res.user, reg_res.group

        parsed = PayCommandParser.parse(cmd_clean)
        if "error" in parsed:
            return (
                f"⚠️ Error parsing command: {parsed['error']}\n"
                f"Usage: `/pay <amount> [for <description>] [by <payer(s)>] [split <participants>] [on <date>]`",
                None,
            )
        try:
            expense = ExpenseService.record_expense(
                session=session,
                group=group,
                sender=sender,
                command=parsed,
            )
        except (UserNotFoundError, ValidationError) as e:
            return f"⚠️ {e}", None

        reply_text = generate_expense_reply_text(expense)
        reply_markup = ExpenseKeyboardBuilder.build_expense_undo_keyboard(
            expense_id=expense.id, creator_id=sender.id
        )
        return reply_text, reply_markup


# Aliases for backwards compatibility
store_pending_voice_command = VoiceService.store_pending_command
get_pending_voice_command = VoiceService.get_pending_command
pop_pending_voice_command = VoiceService.pop_pending_command
clear_pending_voice_commands = VoiceService.clear_pending_commands
