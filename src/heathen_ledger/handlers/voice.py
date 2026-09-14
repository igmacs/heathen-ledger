import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Set
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, MessageEntityType
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from .. import crud
from ..voice import get_voice_interpreter

logger = logging.getLogger(__name__)


@dataclass
class PendingVoiceCommand:
    """Represents an unconfirmed voice command awaiting user action."""

    token: str
    command: str
    creator_id: Optional[int]
    creator_username: Optional[str]
    creator_first_name: Optional[str]
    authorized_user_ids: Set[int]
    chat_id: int
    transcription: str
    created_at: float = field(default_factory=time.time)


_PENDING_VOICE_COMMANDS: dict[str, PendingVoiceCommand] = {}


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
    # Prune expired commands (> 1 hour old)
    now = time.time()
    expired = [
        t for t, p in _PENDING_VOICE_COMMANDS.items() if now - p.created_at > 3600
    ]
    for t in expired:
        _PENDING_VOICE_COMMANDS.pop(t, None)

    token = uuid.uuid4().hex[:10]
    _PENDING_VOICE_COMMANDS[token] = PendingVoiceCommand(
        token=token,
        command=command,
        creator_id=creator_id,
        creator_username=creator_username,
        creator_first_name=creator_first_name,
        authorized_user_ids=authorized_user_ids,
        chat_id=chat_id,
        transcription=transcription,
        created_at=now,
    )
    return token


def get_pending_voice_command(token: str) -> Optional[PendingVoiceCommand]:
    """Retrieve a pending voice command by token."""
    return _PENDING_VOICE_COMMANDS.get(token)


def pop_pending_voice_command(token: str) -> Optional[PendingVoiceCommand]:
    """Atomically pop a pending voice command by token."""
    return _PENDING_VOICE_COMMANDS.pop(token, None)


def clear_pending_voice_commands() -> None:
    """Clear all pending commands (useful for test isolation)."""
    _PENDING_VOICE_COMMANDS.clear()


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
        telegram_file = await context.bot.get_file(media.file_id)
        audio_bytes = bytes(await telegram_file.download_as_bytearray())
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

    # Determine MIME type
    mime_type = getattr(media, "mime_type", None) or (
        "audio/ogg" if media_message.voice else "audio/mpeg"
    )

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
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text="✅ Confirm", callback_data=f"voice:confirm:{token}"
                        ),
                        InlineKeyboardButton(
                            text="❌ Reject", callback_data=f"voice:reject:{token}"
                        ),
                    ]
                ]
            )
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
    """Execute an interpreted bot command and return (reply_text, reply_markup)."""
    # Import locally to avoid circular dependencies between handler modules
    from .expense import build_expense_keyboard
    from .settle import build_settle_keyboard
    from ..formatters import (
        generate_expense_reply_text,
        generate_balances_summary,
        generate_settlements_summary,
        format_cents,
    )
    from ..parser import (
        parse_pay_message,
        parse_payback_message,
        generate_history_summary,
    )
    from ..services import expense_service, settlement_service
    from ..services.exceptions import UserNotFoundError, ValidationError

    cmd_clean = command_str.strip()
    if not cmd_clean.startswith("/"):
        cmd_clean = f"/{cmd_clean}"

    cmd_parts = cmd_clean.split()
    cmd_name = cmd_parts[0].split("@")[0].lower()

    # Resolve group
    group = crud.get_group_by_telegram_id(session, chat_id)
    if not group:
        group = crud.get_or_create_group(session, chat_id, chat_title)

    # Resolve sender
    sender = crud.get_user_by_telegram_id(session, creator_id)
    if not sender:
        sender = crud.get_or_create_user(
            session,
            telegram_id=creator_id,
            username=creator_username,
            first_name=creator_first_name or f"User{creator_id}",
        )
    crud.add_user_to_group(session, sender, group)

    if cmd_name == "/pay":
        parsed = parse_pay_message(cmd_clean)
        if "error" in parsed:
            return (
                f"⚠️ Error parsing command: {parsed['error']}\n"
                f"Usage: `/pay <amount> [for <description>] [by <payer(s)>] [split <participants>] [on <date>]`",
                None,
            )
        try:
            expense = expense_service.record_expense(
                session=session,
                group=group,
                sender=sender,
                command=parsed,
            )
        except (UserNotFoundError, ValidationError) as e:
            return f"⚠️ {e}", None

        reply_text = generate_expense_reply_text(expense)
        reply_markup = build_expense_keyboard(expense, group.members, sender.id)
        return reply_text, reply_markup

    elif cmd_name == "/payback":
        parsed = parse_payback_message(cmd_clean)
        if "error" in parsed:
            return (
                f"⚠️ Error parsing command: {parsed['error']}\n"
                f"Usage: `/payback [@payer] @recipient <amount>`",
                None,
            )
        try:
            payment = expense_service.record_payback(
                session=session,
                group=group,
                sender=sender,
                command=parsed,
            )
        except (UserNotFoundError, ValidationError) as e:
            return f"⚠️ {e}", None

        amount_formatted = format_cents(payment.amount)
        keyboard = [
            [
                InlineKeyboardButton(
                    text="🗑️ Undo",
                    callback_data=f"undo:payment:{payment.id}:{sender.id}",
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        reply_text = (
            f"✅ **Recorded payment:**\n"
            f"• **Paid by:** {payment.payer.first_name}\n"
            f"• **Paid to:** {payment.payee.first_name}\n"
            f"• **Amount:** {amount_formatted}"
        )
        return reply_text, reply_markup

    elif cmd_name == "/balances":
        if not group or not group.members:
            return "ℹ️ No transactions or members recorded for this group yet.", None
        balances, _, users_by_id = (
            settlement_service.get_group_balances_and_settlements(session, group.id)
        )
        reply_text = generate_balances_summary(balances, users_by_id)
        return reply_text, None

    elif cmd_name == "/settle":
        if not group or not group.members:
            return "ℹ️ No transactions or members recorded for this group yet.", None
        _, transactions, users_by_id = (
            settlement_service.get_group_balances_and_settlements(session, group.id)
        )
        reply_text = generate_settlements_summary(transactions, users_by_id)
        reply_markup = build_settle_keyboard(transactions, users_by_id)
        return reply_text, reply_markup

    elif cmd_name == "/history":
        if not group:
            return "ℹ️ No transactions or members recorded for this group yet.", None
        txs = crud.get_recent_transactions(session, group.id, limit=10)
        reply_text = generate_history_summary(txs)
        keyboard = []
        if txs:
            for i, tx in enumerate(txs, 1):
                t_type = tx["type"]
                obj = tx["obj"]
                callback_data = f"hist_del:{t_type}:{obj.id}"
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            text=f"🗑️ Delete {i}", callback_data=callback_data
                        )
                    ]
                )
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        return reply_text, reply_markup

    else:
        return f"⚠️ Unsupported command from voice note: `{cmd_clean}`", None


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

        # Execute command
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
