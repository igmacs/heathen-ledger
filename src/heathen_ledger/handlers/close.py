"""Handler for closing a settled ledger, wiping group records, and leaving the chat."""

import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes

from ..database import with_db_session
from ..formatters import generate_settlements_summary
from ..repositories import GroupRepository
from ..services import SettlementService
from .common import require_group_chat, send_response

logger = logging.getLogger(__name__)


@require_group_chat
@with_db_session
async def close_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /close command to close the ledger, wipe group records, and leave the chat."""
    chat = update.effective_chat
    if not chat:
        return

    group = GroupRepository(session).get_by_telegram_id(chat.id)
    if not group:
        await send_response(
            update,
            context,
            "ℹ️ No active ledger or recorded transactions found for this group.",
        )
        return

    is_settled, transactions, users_by_id = SettlementService.is_group_settled(
        session, group.id
    )
    if not is_settled:
        summary = generate_settlements_summary(transactions, users_by_id)
        reply_text = (
            "⚠️ *Cannot close ledger: there are unsettled debts.*\n\n"
            f"{summary}\n\n"
            "Please settle all debts with `/settle` before closing the ledger."
        )
        await send_response(update, context, reply_text, parse_mode="Markdown")
        return

    # All debts are settled: send public farewell message to the group
    farewell_text = (
        "👋 *All debts are settled! Ledger closed.*\n\n"
        "Group records have been cleared. Add me back anytime you want to start a new ledger. Goodbye!"
    )
    try:
        await send_response(
            update,
            context,
            farewell_text,
            parse_mode="Markdown",
            ephemeral=False,
        )
    except Exception as e:
        logger.warning("Could not send farewell message before leaving: %s", e)

    # Delete group and external members from database
    GroupRepository(session).delete(group)
    session.commit()

    # Leave the group chat
    try:
        if context.bot:
            await context.bot.leave_chat(chat_id=chat.id)
    except Exception as e:
        logger.warning("Failed to leave chat %s: %s", chat.id, e)
