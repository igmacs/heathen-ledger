"""Service layer for voice transcription, interpretation, and pending command lifecycle."""

import logging
from sqlalchemy.orm import Session
from telegram import Bot, Message, InlineKeyboardMarkup
from telegram.constants import ChatAction

from ..voice import (
    get_voice_interpreter,
    PendingVoiceCommand,
    PendingVoiceCommandStore,
    VoiceAudioDownloader,
    VoiceInterpretation,
)
from ..commands import CommandDispatcher
from ..repositories import GroupRepository
from .exceptions import ValidationError

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
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass

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
        """Execute an interpreted bot command and return (reply_text, reply_markup)."""
        return CommandDispatcher.execute(
            command_str=command_str,
            chat_id=chat_id,
            creator_id=creator_id,
            creator_username=creator_username,
            creator_first_name=creator_first_name,
            session=session,
            chat_title=chat_title,
        )


# Aliases for backwards compatibility
store_pending_voice_command = VoiceService.store_pending_command
get_pending_voice_command = VoiceService.get_pending_command
pop_pending_voice_command = VoiceService.pop_pending_command
clear_pending_voice_commands = VoiceService.clear_pending_commands
