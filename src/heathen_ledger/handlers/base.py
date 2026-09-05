import logging
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
        "📜 **History & Audit Logs**\n"
        "• `/history` — View the last 10 transactions logged in the group chat.\n\n"
        "🎙️ **Voice Notes**\n"
        "• Reply to any voice note or audio message with `/voice`, `/pay`, or tag the bot to transcribe and interpret it into a ledger command.\n\n"
        "⚠️ **User Registration:**\n"
        "The bot automatically registers users when they send a message. "
        "Before you can assign a payment/expense to a member, they *must have sent at least one message* in the group."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
