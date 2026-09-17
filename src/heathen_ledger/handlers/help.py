import logging
from telegram import Update
from telegram.ext import ContextTypes

from .common import send_response

logger = logging.getLogger(__name__)


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
