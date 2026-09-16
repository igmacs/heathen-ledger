import logging
from typing import Optional, Set
from telegram import Update, InlineKeyboardMarkup
from telegram.constants import ChatAction, MessageEntityType
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from .. import crud
from ..voice import (
    get_voice_interpreter,
    PendingVoiceCommand,
    PendingVoiceCommandStore,
    VoiceAudioDownloader,
)
from ..commands import CommandDispatcher
from ..keyboards import VoiceKeyboardBuilder

logger = logging.getLogger(__name__)

_VOICE_STORE = PendingVoiceCommandStore()


def store_pending_voice_command(
    command: str,
    creator_id: Optional[int],
    creator_username: Optional[str],
    creator_first_name: Optional[str],
    authorized_user_ids: Set[int],
    chat_id: int,
    transcription: str,
) -> str:
    """Store an unconfirmed voice command and return a short unique token."""
    return _VOICE_STORE.store(
        command=command,
        creator_id=creator_id,
        creator_username=creator_username,
        creator_first_name=creator_first_name,
        authorized_user_ids=authorized_user_ids,
        chat_id=chat_id,
        transcription=transcription,
    )


def get_pending_voice_command(token: str) -> Optional[PendingVoiceCommand]:
    """Retrieve a pending voice command by token."""
    return _VOICE_STORE.get(token)


def pop_pending_voice_command(token: str) -> Optional[PendingVoiceCommand]:
    """Atomically pop a pending voice command by token."""
    return _VOICE_STORE.pop(token)


def clear_pending_voice_commands() -> None:
    """Clear all pending commands (useful for test isolation)."""
    _VOICE_STORE.clear()


async def is_bot_mentioned(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the bot was mentioned in the update message."""
    if not update.message or not update.message.text:
        return False

    bot_username = getattr(context.bot, "username", None)
    if not bot_username and hasattr(context.bot, "get_me"):
        try:
            bot_user = await context.bot.get_me()
            bot_username = getattr(bot_user, "username", None)
        except Exception:
            bot_username = None

    text = update.message.text
    if bot_username:
        if f"@{bot_username.lower()}" in text.lower():
            return True

    entities = update.message.entities or []
    for entity in entities:
        if entity.type == MessageEntityType.MENTION and bot_username:
            mention = text[entity.offset : entity.offset + entity.length]
            if mention.lstrip("@").lower() == bot_username.lower():
                return True
        elif entity.type == MessageEntityType.TEXT_MENTION and entity.user:
            bot_id = getattr(context.bot, "id", None)
            if bot_id and entity.user.id == bot_id:
                return True

    return False


async def process_voice_audio(
    media_message,
    response_message,
    context: ContextTypes.DEFAULT_TYPE,
    session: Session,
    chat_id: int | None = None,
) -> None:
    """Download, transcribe, and interpret audio/voice from media_message and send response via response_message."""
    media = media_message.voice or media_message.audio
    if not media:
        return

    # Check if a voice interpreter can be instantiated (GEMINI_API_KEY check)
    try:
        interpreter = get_voice_interpreter()
    except ValueError:
        await response_message.reply_text(
            "⚠️ Voice message received, but `GEMINI_API_KEY` is not configured.\n"
            "Please set `GEMINI_API_KEY` in your `.env` to enable voice transcription and command recognition."
        )
        return

    if chat_id is None:
        target_chat = getattr(response_message, "chat", None)
        if target_chat and hasattr(target_chat, "id"):
            chat_id = target_chat.id

    # Indicate typing activity
    if chat_id is not None:
        try:
            await context.bot.send_chat_action(
                chat_id=chat_id,
                action=ChatAction.TYPING,
            )
        except Exception:
            pass

    # Download audio bytes
    try:
        audio_bytes, mime_type = await VoiceAudioDownloader.download(
            context.bot, media_message
        )
    except Exception as e:
        logger.exception("Failed to download voice/audio file from Telegram")
        await response_message.reply_text(
            f"❌ Failed to download audio from Telegram: {e}"
        )
        return

    # Gather group members context
    group_members = []
    if chat_id is not None:
        group = crud.get_group_by_telegram_id(session, chat_id)
        if group and group.members:
            for member in group.members:
                if member.username:
                    group_members.append(f"@{member.username}")
                elif member.first_name:
                    group_members.append(member.first_name)

    # Transcribe and interpret
    try:
        interpretation = await interpreter.interpret(
            audio_bytes,
            group_members=group_members,
            mime_type=mime_type,
        )
    except Exception as e:
        logger.exception("Error processing voice message with Gemini")
        await response_message.reply_text(
            f"❌ Failed to transcribe or interpret audio: {e}"
        )
        return

    # Format response
    reply_lines = [f'🎙️ *Transcription:*\n"{interpretation.transcription}"']
    reply_markup = None

    if interpretation.command:
        reply_lines.append(f"\n💡 *Interpreted Command:*\n`{interpretation.command}`")

        speaker = getattr(media_message, "from_user", None) or getattr(
            response_message, "from_user", None
        )
        requester = getattr(response_message, "from_user", None)

        creator_id = getattr(speaker, "id", None)
        creator_username = getattr(speaker, "username", None)
        creator_first_name = getattr(speaker, "first_name", None)

        authorized_user_ids: Set[int] = set()
        if creator_id is not None:
            authorized_user_ids.add(creator_id)
        if requester and getattr(requester, "id", None) is not None:
            authorized_user_ids.add(requester.id)

        if chat_id is not None:
            token = store_pending_voice_command(
                command=interpretation.command,
                creator_id=creator_id,
                creator_username=creator_username,
                creator_first_name=creator_first_name,
                authorized_user_ids=authorized_user_ids,
                chat_id=chat_id,
                transcription=interpretation.transcription,
            )
            reply_markup = VoiceKeyboardBuilder.build_confirmation_keyboard(token)
    else:
        reply_lines.append("\n❓ _No ledger command was recognized from this message._")

    await response_message.reply_text(
        "\n".join(reply_lines),
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


@with_db_session
async def voice_command_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle /voice command: process replied-to voice/audio message."""
    if not update.message:
        return

    reply_to = update.message.reply_to_message
    if not reply_to:
        await update.message.reply_text(
            "💡 To process a voice note, reply to an audio or voice message with `/voice`, `/pay`, or tag the bot.",
            parse_mode="Markdown",
        )
        return

    media = reply_to.voice or reply_to.audio
    if not media:
        await update.message.reply_text(
            "⚠️ The replied message does not contain a voice note or audio file."
        )
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    await process_voice_audio(
        media_message=reply_to,
        response_message=update.message,
        context=context,
        session=session,
        chat_id=chat_id,
    )


@with_db_session
async def voice_mention_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle mentions in replies to voice/audio messages."""
    if not update.message:
        return

    reply_to = update.message.reply_to_message
    if not reply_to:
        return

    media = reply_to.voice or reply_to.audio
    if not media:
        return

    if not await is_bot_mentioned(update, context):
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    await process_voice_audio(
        media_message=reply_to,
        response_message=update.message,
        context=context,
        session=session,
        chat_id=chat_id,
    )


@with_db_session
async def voice_message_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle incoming voice/audio messages directly (for backwards compatibility/direct calls)."""
    if not update.message:
        return

    media = update.message.voice or update.message.audio
    if not media:
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    await process_voice_audio(
        media_message=update.message,
        response_message=update.message,
        context=context,
        session=session,
        chat_id=chat_id,
    )


def execute_voice_command(
    command_str: str,
    chat_id: int,
    creator_id: int,
    creator_username: Optional[str],
    creator_first_name: Optional[str],
    session: Session,
    chat_title: Optional[str] = None,
) -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """Execute an interpreted bot command and return (reply_text, reply_markup).

    Delegates to CommandDispatcher.
    """
    return CommandDispatcher.execute(
        command_str=command_str,
        chat_id=chat_id,
        creator_id=creator_id,
        creator_username=creator_username,
        creator_first_name=creator_first_name,
        session=session,
        chat_title=chat_title,
    )


@with_db_session
async def voice_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle callback queries for voice command confirmation or rejection."""
    query = update.callback_query
    if not query or not query.data:
        return

    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "voice":
        return

    action = parts[1]
    token = parts[2]

    pending = get_pending_voice_command(token)
    if not pending:
        await query.answer(
            text="⚠️ This command has expired or was already processed.",
            show_alert=True,
        )
        if query.message:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except BadRequest:
                pass
        return

    # Check permission
    if (
        pending.authorized_user_ids
        and query.from_user.id not in pending.authorized_user_ids
    ):
        await query.answer(
            text="⚠️ Only the person who sent or requested this voice command can confirm or reject it.",
            show_alert=True,
        )
        return

    # Atomically pop so it cannot be double-processed
    pop_pending_voice_command(token)

    if action == "reject":
        await query.answer(text="Command rejected.")
        rejected_text = (
            f'🎙️ *Transcription:*\n"{pending.transcription}"\n\n'
            f"💡 *Interpreted Command:*\n`{pending.command}`\n\n"
            f"❌ *Rejected*"
        )
        try:
            await query.edit_message_text(
                text=rejected_text,
                parse_mode="Markdown",
                reply_markup=None,
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        return

    if action == "confirm":
        await query.answer(text="Executing command...")
        confirmed_text = (
            f'🎙️ *Transcription:*\n"{pending.transcription}"\n\n'
            f"💡 *Interpreted Command:*\n`{pending.command}`\n\n"
            f"✅ *Confirmed and executed*"
        )
        try:
            await query.edit_message_text(
                text=confirmed_text,
                parse_mode="Markdown",
                reply_markup=None,
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise

        # Execute command via CommandDispatcher
        chat_title = None
        if query.message and query.message.chat:
            chat_title = getattr(query.message.chat, "title", None)

        creator_id = pending.creator_id or query.from_user.id
        creator_username = pending.creator_username or query.from_user.username
        creator_first_name = pending.creator_first_name or query.from_user.first_name

        reply_text, reply_markup = execute_voice_command(
            command_str=pending.command,
            chat_id=pending.chat_id,
            creator_id=creator_id,
            creator_username=creator_username,
            creator_first_name=creator_first_name,
            session=session,
            chat_title=chat_title,
        )

        if query.message:
            await query.message.reply_text(
                text=reply_text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
        else:
            await context.bot.send_message(
                chat_id=pending.chat_id,
                text=reply_text,
                parse_mode="Markdown",
                reply_markup=reply_markup,
            )
