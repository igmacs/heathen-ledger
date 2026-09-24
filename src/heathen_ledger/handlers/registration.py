import logging
import re

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import MessageEntityType
from telegram.ext import ContextTypes

from ..database import with_db_session
from ..services import MemberRegistrationService
from .common import is_group_chat, require_group_chat, send_response

logger = logging.getLogger(__name__)


@with_db_session
async def auto_register(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Automatically register the user and group chat if they don't exist yet."""
    if not update.effective_chat or not update.effective_user:
        return

    # Skip bots
    if update.effective_user.is_bot:
        return

    # Only register in group/supergroup chats
    if not is_group_chat(update):
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name or ""
    title = update.effective_chat.title or f"Chat ({chat_id})"

    MemberRegistrationService.auto_register_user_and_group(
        session=session,
        user_id=user_id,
        chat_id=chat_id,
        username=username,
        first_name=first_name,
        chat_title=title,
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
    _, group = MemberRegistrationService.ensure_member_in_group(
        session=session,
        chat_id=chat.id,
        user_id=update.effective_user.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name or "",
        chat_title=chat.title,
    )

    # 1. Replying to a message: register the author of that message
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
        _, msg = MemberRegistrationService.register_reply_user(
            session, group, target_user
        )
        await send_response(update, context, msg, parse_mode="Markdown")
        return

    # 2. Text mention entities (users without username or chosen from Telegram picker)
    text_mentions = [
        e
        for e in (update.message.entities or [])
        if e.type == MessageEntityType.TEXT_MENTION and e.user
    ]
    if text_mentions:
        registered_names, already_registered_names = (
            MemberRegistrationService.register_text_mentions(
                session, group, text_mentions
            )
        )
        msgs = []
        if registered_names:
            msgs.append(
                f"✅ Registered member(s): {', '.join(f'*{n}*' for n in registered_names)} to this group ledger."
            )
        if already_registered_names:
            msgs.append(
                f"ℹ️ Already registered: {', '.join(f'*{n}*' for n in already_registered_names)}."
            )
        await send_response(
            update,
            context,
            "\n".join(msgs) if msgs else "⚠️ No valid users found to register.",
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
    all_mentions = [p.lstrip("@").lower() for p in parts if p.startswith("@")]
    if len(all_mentions) > 1 and len(all_mentions) == len(parts):
        admins_by_username = await MemberRegistrationService.get_admins_by_username(
            context, chat.id
        )
        registered, already_registered = MemberRegistrationService.register_mentions(
            session, group, all_mentions, admins_by_username
        )
        msgs = []
        if registered:
            msgs.append(f"✅ Registered member(s): {', '.join(registered)}.")
        if already_registered:
            msgs.append(f"ℹ️ Already registered: {', '.join(already_registered)}.")
        await send_response(update, context, "\n".join(msgs), parse_mode="Markdown")
        return

    first_token = parts[0]
    if first_token.startswith("@"):
        handle = first_token.lstrip("@").lower()
        first_name = (
            " ".join(parts[1:]).strip() if len(parts) > 1 else handle.capitalize()
        )
        admin_u = await MemberRegistrationService.resolve_admin_by_username(
            context, chat.id, handle
        )
        msg = MemberRegistrationService.register_handle(
            session, group, handle, first_name, admin_u
        )
        await send_response(update, context, msg, parse_mode="Markdown")
        return
    else:
        _, msg = MemberRegistrationService.register_name(session, group, args_text)
        await send_response(update, context, msg, parse_mode="Markdown")


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

    chat_title = chat.title or f"Chat ({chat.id})"
    already_registered, _, _ = MemberRegistrationService.register_self(
        session=session,
        chat_id=chat.id,
        user=user,
        chat_title=chat_title,
    )

    if already_registered:
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
