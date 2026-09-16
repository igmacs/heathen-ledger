import logging
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, MessageEntityType
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from .. import crud
from ..services import MemberRegistrationService
from .common import send_response

logger = logging.getLogger(__name__)


async def _resolve_admin_by_username(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, username: str
):
    """Helper to check if a username matches a chat administrator."""
    return await MemberRegistrationService.resolve_admin_by_username(
        context, chat_id, username
    )


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

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    title = update.effective_chat.title or f"Private Chat ({user_id})"

    db_user = crud.get_or_create_user(session, user_id, username, first_name)
    db_group = crud.get_or_create_group(session, chat_id, title)
    crud.add_user_to_group(session, db_user, db_group)


@with_db_session
async def register_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Register a member, external person, or display registration button for the group ledger."""
    if not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    group = crud.get_group_by_telegram_id(session, chat.id)
    if not group:
        group = crud.get_or_create_group(
            session,
            chat.id,
            chat.title or f"Chat ({chat.id})",
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
        if chat.type == ChatType.PRIVATE:
            await send_response(
                update,
                context,
                "ℹ️ In private chat, you are already registered with the bot! Add me to a group chat and use `/register` to register group members.",
                parse_mode="Markdown",
            )
            return

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

    group = crud.get_group_by_telegram_id(session, chat.id)
    if not group:
        title = chat.title or f"Chat ({chat.id})"
        group = crud.get_or_create_group(session, chat.id, title)

    # Check if user is already registered in this group
    if any(m.telegram_id == user.id for m in group.members):
        await query.answer(
            f"ℹ️ You are already registered as {user.first_name}!", show_alert=False
        )
        return

    db_user = crud.get_or_create_user(
        session,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )
    crud.add_user_to_group(session, db_user, group)
    session.commit()

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


@with_db_session
async def members_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """List all registered members in the current group ledger."""
    if not update.effective_chat or not update.message:
        return

    group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
    if not group or not group.members:
        await send_response(
            update,
            context,
            "ℹ️ No members are currently registered in this group ledger.",
        )
        return

    lines = ["👥 **Group Members:**\n"]
    for idx, m in enumerate(group.members, 1):
        handle = f" (@{m.username})" if m.username else ""
        ext_tag = " _[external]_" if m.is_external else ""
        lines.append(f"{idx}. **{m.first_name}**{handle}{ext_tag}")

    await send_response(update, context, "\n".join(lines), parse_mode="Markdown")


@with_db_session
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    """Send a message when the command /start is issued."""
    await send_response(
        update,
        context,
        "👋 **Hello! I am Heathen Ledger.**\n\n"
        '_*"This group deserves a better class of ledger, and I’m gonna give it to ‘em."*_\n\n'
        "I help you track and settle shared expenses in group chats. Type /help to see all available commands.",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command to display instructions and formatting."""
    help_text = (
        "📖 **Heathen Ledger Bot Help**\n\n"
        "Here are the available commands:\n\n"
        "💸 **Logging Expenses**\n"
        "• `/pay <amount> [for <description>]` — Log an expense paid by you, split equally among everyone. (e.g. `/pay 12.50 for Pizza`)\n"
        "• `/pay @payer <amount> [for <description>]` — Log an expense paid by another member, split equally. (e.g. `/pay @Alice 50 for Dinner`)\n"
        "• `/pay @payer <amount> for @user1 @user2 ...` — Log an expense split specifically among selected members. (e.g. `/pay @Alice 50 for @Bob @Charlie`)\n\n"
        "🤝 **Settle Debts & Paybacks**\n"
        "• `/balances` — View current net group balances (highest creditor to highest debtor).\n"
        "• `/settle` — Calculate the minimum payback transactions needed to settle all group debts.\n"
        "• `/payback @recipient <amount>` — Record a direct payment from you to settle up. (e.g. `/payback @Alice 10`)\n"
        "• `/payback @payer @recipient <amount>` — Record a direct payment between other group members. (e.g. `/payback @Bob @Alice 12.50`)\n\n"
        "👥 **Members & Registration (Privacy Mode Compatible)**\n"
        "• `/members` — List all members in this group ledger.\n"
        "• `/register` — Post an inline button for members to tap and register themselves.\n"
        "• `/register @handle` or `/register <name>` — Register a group member or external user (or reply to their message with `/register`).\n\n"
        "📜 **History & Audit Logs**\n"
        "• `/history` — View the last 10 transactions logged in the group chat.\n\n"
        "🎙️ **Voice Notes**\n"
        "• Reply to any voice note or audio message with `/voice`, `/pay`, or tag the bot to transcribe and interpret it into a ledger command.\n\n"
        "👻 **Ephemeral Responses & Sharing**\n"
        "• All commands and responses in groups are **ephemeral** (visible only to you) by default to keep the chat clean.\n"
        "• Tap **📢 Share to group** on any ephemeral response to delete the preview and publish it publicly to the whole group.\n"
        "• Tap **✕ Dismiss** to delete the ephemeral message from your view.\n\n"
        "⚠️ **User Registration:**\n"
        "Members can tap the button from `/register`, be registered via `/register @handle`, or be registered by replying to their message with `/register`."
    )
    await send_response(update, context, help_text, parse_mode="Markdown")
