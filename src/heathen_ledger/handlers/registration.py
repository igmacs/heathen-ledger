import logging
import re

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import MessageEntityType
from telegram.ext import ContextTypes

from ..database import with_db_session
from ..services import (
    MemberRegistrationService,
    RegistrationBatchResult,
    RegistrationResult,
)
from .common import is_group_chat, require_group_chat, send_response

logger = logging.getLogger(__name__)


def format_registration_result(res: RegistrationResult) -> str:
    """Format a single registration result into a user-facing Telegram Markdown message."""
    if not res.success:
        return f"⚠️ {res.error}"
    if not res.user:
        return ""

    handle_str = f" (`@{res.user.username}`)" if res.user.username else ""
    if res.already_registered:
        return f"ℹ️ Member *{res.user.first_name}*{handle_str} is already registered in this group."

    if not res.user.is_external:
        return f"✅ Registered member *{res.user.first_name}*{handle_str} to this group ledger."

    # External member
    if res.has_explicit_handle:
        return (
            f"✅ Registered *{res.user.first_name}*{handle_str} in this group ledger.\n\n"
            f"They can now be included in expenses and settlements. "
            f"When @{res.user.username} interacts with the bot or taps Register, their account will link automatically."
        )
    return (
        f"✅ Registered external member *{res.user.first_name}*{handle_str} to this group.\n\n"
        f"You can now include them in expenses (e.g. `/pay 50 split @{res.user.username}`) or settlements."
    )


def format_batch_registration_result(batch: RegistrationBatchResult) -> str:
    """Format a batch registration result into a user-facing Telegram Markdown message."""
    msgs = []
    reg_labels = [
        r.display_label
        for r in batch.results
        if r.success and not r.already_registered and r.display_label
    ]
    already_labels = [
        r.display_label
        for r in batch.results
        if r.success and r.already_registered and r.display_label
    ]

    if reg_labels:
        msgs.append(f"✅ Registered member(s): {', '.join(reg_labels)}.")
    if already_labels:
        msgs.append(f"ℹ️ Already registered: {', '.join(already_labels)}.")

    return "\n".join(msgs) if msgs else "⚠️ No valid users found to register."


@with_db_session
async def auto_register(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Automatically register the user in the group ledger if they don't exist yet."""
    if not update.effective_chat or not update.effective_user:
        return

    # Skip bots
    if update.effective_user.is_bot:
        return

    # Only register in group/supergroup chats
    if not is_group_chat(update):
        return

    # Skip self-registration callback so register_callback_handler can handle new join announcements
    if update.callback_query and (update.callback_query.data or "").startswith(
        "register:"
    ):
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name or ""

    MemberRegistrationService.register_user(
        session=session,
        group=chat_id,
        target=user_id,
        username=username,
        first_name=first_name,
    )


@require_group_chat
@with_db_session
async def register_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Register a member, external person, or display registration button for the group ledger."""
    if not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    res = MemberRegistrationService.register_user(
        session=session,
        group=chat.id,
        target=update.effective_user.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name or "",
    )
    group = res.group

    # 1. Replying to a message: register the author of that message
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
        res = MemberRegistrationService.register_user(session, group, target_user)
        await send_response(
            update, context, format_registration_result(res), parse_mode="Markdown"
        )
        return

    # 2. Text mention entities (users without username or chosen from Telegram picker)
    text_mentions = [
        e
        for e in (update.message.entities or [])
        if e.type == MessageEntityType.TEXT_MENTION and e.user
    ]
    if text_mentions:
        batch = MemberRegistrationService.register_users(
            session, group, [e.user for e in text_mentions]
        )
        await send_response(
            update,
            context,
            format_batch_registration_result(batch),
            parse_mode="Markdown",
        )
        return

    text = update.message.text.strip()
    args_text = re.sub(
        r"^/register(?:_persistent)?(?:@\w+)?\s*", "", text, flags=re.IGNORECASE
    ).strip()

    # 3. No parameters: show inline button to let members register themselves
    if not args_text:
        keyboard = [
            [InlineKeyboardButton("📝 Register me", callback_data="register:join")]
        ]
        await send_response(
            update,
            context,
            "📝 **Member Registration**\n\n"
            "Tap the button below to register in this group ledger:\n\n"
            "_Tip: You can also register others by mentioning them (e.g. `/register @handle`) or replying to their message with `/register`._",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return

    # 4. Parameters provided: mentions or names
    parts = args_text.split()

    # Check if multiple @mentions are given (e.g. /register @alice @bob)
    all_mentions = [p for p in parts if p.startswith("@")]
    if len(all_mentions) > 1 and len(all_mentions) == len(parts):
        batch = MemberRegistrationService.register_users(session, group, all_mentions)
        await send_response(
            update,
            context,
            format_batch_registration_result(batch),
            parse_mode="Markdown",
        )
        return

    first_token = parts[0]
    if first_token.startswith("@"):
        first_name = " ".join(parts[1:]).strip() if len(parts) > 1 else None
        res = MemberRegistrationService.register_user(
            session, group, first_token, first_name=first_name
        )
        await send_response(
            update, context, format_registration_result(res), parse_mode="Markdown"
        )
        return
    else:
        res = MemberRegistrationService.register_user(session, group, args_text)
        await send_response(
            update, context, format_registration_result(res), parse_mode="Markdown"
        )


@with_db_session
async def register_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle inline button click for member self-registration."""
    query = update.callback_query
    if not query or not query.from_user:
        return

    user = query.from_user
    if user.is_bot:
        await query.answer("⚠️ Bots cannot be registered.", show_alert=True)
        return

    chat = query.message.chat if query.message else update.effective_chat
    if not chat:
        await query.answer()
        return

    res = MemberRegistrationService.register_user(
        session=session,
        group=chat.id,
        target=user,
    )

    if res.already_registered:
        await query.answer(
            f"ℹ️ You are already registered as {user.first_name}!", show_alert=False
        )
        return

    await query.answer(
        f"✅ You are now registered as {user.first_name}!", show_alert=False
    )
    handle_str = f" (@{user.username})" if user.username else ""
    if query.message:
        await query.message.reply_text(
            f"👋 Registered *{user.first_name}*{handle_str} to the group ledger!",
            parse_mode="Markdown",
        )
    elif hasattr(context, "bot") and hasattr(context.bot, "send_message"):
        await context.bot.send_message(
            chat_id=chat.id,
            text=f"👋 Registered *{user.first_name}*{handle_str} to the group ledger!",
            parse_mode="Markdown",
        )
