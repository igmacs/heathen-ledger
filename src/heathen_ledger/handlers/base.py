import logging
import re
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from .. import crud

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
    """Register an external member (without Telegram) into the current group."""
    if not update.message or not update.effective_chat:
        return

    text = update.message.text.strip()
    args_text = re.sub(r"^/register(?:@\w+)?\s*", "", text, flags=re.IGNORECASE).strip()

    if not args_text:
        await update.message.reply_text(
            "⚠️ Please specify a name for the external member.\n\n"
            "**Usage:**\n"
            "• `/register <name>` (e.g. `/register John`)\n"
            "• `/register @handle <name>` (e.g. `/register @john John Doe`)\n"
            "• `/register <First Last>` (e.g. `/register John Doe` -> handle `@john_doe`)",
            parse_mode="Markdown",
        )
        return

    group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
    if not group:
        group = crud.get_or_create_group(
            session,
            update.effective_chat.id,
            update.effective_chat.title or f"Chat ({update.effective_chat.id})",
        )

    parts = args_text.split()
    first_token = parts[0]

    if first_token.startswith("@"):
        handle = first_token.lstrip("@").lower()
        if len(parts) > 1:
            first_name = " ".join(parts[1:]).strip()
        else:
            first_name = handle.capitalize()
    else:
        if len(parts) == 1:
            first_name = first_token
            handle = re.sub(r"[^\w]", "", first_token).lower()
        else:
            first_name = args_text
            handle = re.sub(r"[^\w]+", "_", args_text).strip("_").lower()

    if not handle:
        await update.message.reply_text(
            "⚠️ Invalid handle or name. Please use alphanumeric characters."
        )
        return

    # Check for duplicate handles within this group
    for m in group.members:
        if m.username and m.username.lower() == handle:
            await update.message.reply_text(
                f"⚠️ A member with handle @{handle} already exists in this group ({m.first_name})."
            )
            return

    crud.create_external_user(
        session=session,
        group=group,
        first_name=first_name,
        username=handle,
    )
    session.commit()

    await update.message.reply_text(
        f"✅ Registered external member *{first_name}* (`@{handle}`) to this group.\n\n"
        f"You can now include them in expenses (e.g. `/pay 50 split @{handle}`) or settlements.",
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
        await update.message.reply_text(
            "ℹ️ No members are currently registered in this group ledger."
        )
        return

    lines = ["👥 **Group Members:**\n"]
    for idx, m in enumerate(group.members, 1):
        handle = f" (@{m.username})" if m.username else ""
        ext_tag = " _[external]_" if m.is_external else ""
        lines.append(f"{idx}. **{m.first_name}**{handle}{ext_tag}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


@with_db_session
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    """Send a message when the command /start is issued."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "👋 **Hello! I am Heathen Ledger.**\n\n"
            '_*"This group deserves a better class of ledger, and I’m gonna give it to ‘em."*_\n\n'
            "I help you track and settle shared expenses in group chats. Type /help to see all available commands."
        ),
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
        "👥 **Members & External Users**\n"
        "• `/members` — List all members in this group ledger.\n"
        "• `/register <name>` or `/register @handle <name>` — Register an external member who doesn't have Telegram (e.g. `/register @john John Doe`).\n\n"
        "📜 **History & Audit Logs**\n"
        "• `/history` — View the last 10 transactions logged in the group chat.\n\n"
        "🎙️ **Voice Notes**\n"
        "• Reply to any voice note or audio message with `/voice`, `/pay`, or tag the bot to transcribe and interpret it into a ledger command.\n\n"
        "⚠️ **User Registration:**\n"
        "The bot automatically registers Telegram users when they send a message. "
        "Non-Telegram members can be registered manually using `/register <name>`."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
