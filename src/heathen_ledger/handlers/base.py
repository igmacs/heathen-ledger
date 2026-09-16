import asyncio
import logging
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, MessageEntityType
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from ..models import User
from .. import crud
from .common import send_response

logger = logging.getLogger(__name__)


async def _resolve_admin_by_username(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int, username: str
):
    """Helper to check if a username matches a chat administrator."""
    clean_username = username.lower().lstrip("@")
    if hasattr(context, "bot") and hasattr(context.bot, "get_chat_administrators"):
        try:
            res = context.bot.get_chat_administrators(chat_id)
            admins = await res if asyncio.iscoroutine(res) else res
            if isinstance(admins, (list, tuple)):
                for adm in admins:
                    adm_u = getattr(adm, "user", None)
                    if adm_u and getattr(adm_u, "username", None):
                        if adm_u.username.lower() == clean_username:
                            return adm_u
        except Exception as e:
            logger.debug(f"Could not fetch chat administrators: {e}")
    return None


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
        if target_user.is_bot:
            await send_response(update, context, "⚠️ Cannot register a bot.")
            return

        if any(m.telegram_id == target_user.id for m in group.members):
            handle_str = f" (`@{target_user.username}`)" if target_user.username else ""
            await send_response(
                update,
                context,
                f"ℹ️ Member *{target_user.first_name}*{handle_str} is already registered in this group.",
                parse_mode="Markdown",
            )
            return

        db_user = crud.get_or_create_user(
            session,
            telegram_id=target_user.id,
            username=target_user.username,
            first_name=target_user.first_name,
        )
        crud.add_user_to_group(session, db_user, group)
        session.commit()

        handle_str = f" (`@{target_user.username}`)" if target_user.username else ""
        await send_response(
            update,
            context,
            f"✅ Registered member *{target_user.first_name}*{handle_str} to this group ledger.",
            parse_mode="Markdown",
        )
        return

    # 2. Text mention entities (users without username or chosen from Telegram picker)
    text_mentions = [
        e
        for e in (update.message.entities or [])
        if e.type == MessageEntityType.TEXT_MENTION and e.user
    ]
    if text_mentions:
        registered_names = []
        already_registered_names = []
        for tm in text_mentions:
            u = tm.user
            if u.is_bot:
                continue
            if any(m.telegram_id == u.id for m in group.members):
                already_registered_names.append(u.first_name)
                continue
            db_u = crud.get_or_create_user(
                session, telegram_id=u.id, username=u.username, first_name=u.first_name
            )
            crud.add_user_to_group(session, db_u, group)
            registered_names.append(u.first_name)
        session.commit()

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
        registered = []
        already_registered = []

        admins_by_username = {}
        if hasattr(context, "bot") and hasattr(context.bot, "get_chat_administrators"):
            try:
                res = context.bot.get_chat_administrators(chat.id)
                admins = await res if asyncio.iscoroutine(res) else res
                if isinstance(admins, (list, tuple)):
                    for adm in admins:
                        adm_u = getattr(adm, "user", None)
                        if adm_u and getattr(adm_u, "username", None):
                            admins_by_username[adm_u.username.lower()] = adm_u
            except Exception as e:
                logger.debug(f"Could not fetch chat admins: {e}")

        for h in all_mentions:
            if any(m.username and m.username.lower() == h for m in group.members):
                already_registered.append(f"@{h}")
                continue
            if h in admins_by_username:
                adm_u = admins_by_username[h]
                db_u = crud.get_or_create_user(
                    session, adm_u.id, adm_u.username, adm_u.first_name
                )
                crud.add_user_to_group(session, db_u, group)
                registered.append(f"@{h}")
                continue
            glob_u = (
                session.query(User)
                .filter(User.username == h, User.is_external.is_(False))
                .first()
            )
            if glob_u:
                crud.add_user_to_group(session, glob_u, group)
                registered.append(f"@{h}")
                continue
            # Register as external/pending user
            crud.create_external_user(session, group, h.capitalize(), username=h)
            registered.append(f"@{h}")
        session.commit()

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
        if len(parts) > 1:
            first_name = " ".join(parts[1:]).strip()
        else:
            first_name = handle.capitalize()

        # Check for duplicate handles within this group
        for m in group.members:
            if m.username and m.username.lower() == handle:
                await send_response(
                    update,
                    context,
                    f"ℹ️ Member *{m.first_name}* (`@{handle}`) is already registered in this group.",
                    parse_mode="Markdown",
                )
                return

        # Check if chat administrator
        admin_u = await _resolve_admin_by_username(context, chat.id, handle)
        if admin_u:
            db_u = crud.get_or_create_user(
                session, admin_u.id, admin_u.username, admin_u.first_name
            )
            crud.add_user_to_group(session, db_u, group)
            session.commit()
            await send_response(
                update,
                context,
                f"✅ Registered member *{db_u.first_name}* (`@{handle}`) to this group ledger.",
                parse_mode="Markdown",
            )
            return

        # Check if registered Telegram user globally
        glob_u = (
            session.query(User)
            .filter(User.username == handle, User.is_external.is_(False))
            .first()
        )
        if glob_u:
            crud.add_user_to_group(session, glob_u, group)
            session.commit()
            await send_response(
                update,
                context,
                f"✅ Registered member *{glob_u.first_name}* (`@{handle}`) to this group ledger.",
                parse_mode="Markdown",
            )
            return

        # Register external / pending user
        crud.create_external_user(
            session=session,
            group=group,
            first_name=first_name,
            username=handle,
        )
        session.commit()

        await send_response(
            update,
            context,
            f"✅ Registered *{first_name}* (`@{handle}`) in this group ledger.\n\n"
            f"They can now be included in expenses and settlements. "
            f"When @{handle} interacts with the bot or taps Register, their account will link automatically.",
            parse_mode="Markdown",
        )
        return
    else:
        # Register external user without handle (e.g. /register John or /register John Doe)
        if len(parts) == 1:
            first_name = first_token
            handle = re.sub(r"[^\w]", "", first_token).lower()
        else:
            first_name = args_text
            handle = re.sub(r"[^\w]+", "_", args_text).strip("_").lower()

        if not handle:
            await send_response(
                update,
                context,
                "⚠️ Invalid handle or name. Please use alphanumeric characters.",
            )
            return

        # Check for duplicate handles within this group
        for m in group.members:
            if m.username and m.username.lower() == handle:
                await send_response(
                    update,
                    context,
                    f"ℹ️ Member *{m.first_name}* (`@{handle}`) is already registered in this group.",
                    parse_mode="Markdown",
                )
                return

        crud.create_external_user(
            session=session,
            group=group,
            first_name=first_name,
            username=handle,
        )
        session.commit()

        await send_response(
            update,
            context,
            f"✅ Registered external member *{first_name}* (`@{handle}`) to this group.\n\n"
            f"You can now include them in expenses (e.g. `/pay 50 split @{handle}`) or settlements.",
            parse_mode="Markdown",
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
        "👻 **Ephemeral & Persistent Commands**\n"
        "• All commands and responses in groups are **ephemeral** (visible only to you) by default to avoid cluttering the chat.\n"
        "• Add `_persistent` to any reporting command (e.g., `/settle_persistent`, `/balances_persistent`, `/history_persistent`, `/register_persistent`, `/pay_persistent`) to publish the response publicly to the whole group!\n\n"
        "⚠️ **User Registration:**\n"
        "Members can tap the button from `/register` or `/register_persistent`, be registered via `/register @handle`, or be registered by replying to their message with `/register`."
    )
    await send_response(update, context, help_text, parse_mode="Markdown")
