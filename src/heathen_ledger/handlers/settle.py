"""Handlers for balance inquiries, debt settlements, and interactive payback confirmations."""

import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from ..database import with_db_session
from ..formatters import (
    format_cents,
    generate_balances_summary,
    generate_settlements_summary,
)
from ..keyboards import SettlementKeyboardBuilder
from ..models import User
from ..repositories import GroupRepository, UserRepository
from ..services import SettlementService
from ..services.exceptions import PermissionDeniedError
from .common import send_response

logger = logging.getLogger(__name__)

# Backward-compatible alias
build_settle_keyboard = SettlementKeyboardBuilder.build_settle_keyboard


@with_db_session
async def balances_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /balances command to show net group balances."""
    if not update.effective_chat:
        return

    group = GroupRepository(session).get_by_telegram_id(update.effective_chat.id)
    if not group or not group.members:
        await send_response(
            update,
            context,
            "ℹ️ No transactions or members recorded for this group yet.",
        )
        return

    balances, _, users_by_id = SettlementService.get_group_balances_and_settlements(
        session, group.id
    )
    reply_text = generate_balances_summary(balances, users_by_id)
    await send_response(update, context, reply_text, parse_mode="Markdown")


@with_db_session
async def settle_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /settle command to show simplified payback transactions."""
    if not update.effective_chat:
        return

    group = GroupRepository(session).get_by_telegram_id(update.effective_chat.id)
    if not group or not group.members:
        await send_response(
            update,
            context,
            "ℹ️ No transactions or members recorded for this group yet.",
        )
        return

    _, transactions, users_by_id = SettlementService.get_group_balances_and_settlements(
        session, group.id
    )
    reply_text = generate_settlements_summary(transactions, users_by_id)
    reply_markup = SettlementKeyboardBuilder.build_settle_keyboard(
        transactions, users_by_id
    )

    await send_response(
        update,
        context,
        reply_text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


@with_db_session
async def settle_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle callback query when a settle payment confirmation button is clicked."""
    query = update.callback_query
    if not query:
        return

    data = query.data
    if not data or not data.startswith("settle:"):
        return

    try:
        parts = data.split(":")
        from_id = int(parts[1])
        to_id = int(parts[2])
        amount = int(parts[3])
    except (ValueError, IndexError):
        await query.answer(text="⚠️ Error parsing payment details.", show_alert=True)
        return

    if not query.message or not query.message.chat:
        return

    group = GroupRepository(session).get_by_telegram_id(query.message.chat.id)
    if not group:
        await query.answer(text="⚠️ Group not found in database.", show_alert=True)
        return

    # Security check: verify clicking user's role
    clicking_user = UserRepository(session).get_by_telegram_id(query.from_user.id)
    if not clicking_user:
        await query.answer(
            text="⚠️ You are not registered in this group yet. Send a message first!",
            show_alert=True,
        )
        return

    try:
        SettlementService.record_settlement_payment(
            session=session,
            group=group,
            clicking_user=clicking_user,
            from_id=from_id,
            to_id=to_id,
            amount=amount,
        )
    except PermissionDeniedError as e:
        await query.answer(text=f"⚠️ {e}", show_alert=True)
        return

    # Re-calculate balances and settlements
    _, transactions, users_by_id = SettlementService.get_group_balances_and_settlements(
        session, group.id
    )
    reply_text = generate_settlements_summary(transactions, users_by_id)
    reply_markup = SettlementKeyboardBuilder.build_settle_keyboard(
        transactions, users_by_id
    )

    # Inform Telegram that the callback was handled
    from_db_user = session.query(User).filter(User.id == from_id).first()
    to_db_user = session.query(User).filter(User.id == to_id).first()
    from_name = from_db_user.first_name if from_db_user else "Debtor"
    to_name = to_db_user.first_name if to_db_user else "Creditor"
    amount_formatted = format_cents(amount)
    await query.answer(text=f"Recorded: {from_name} paid {to_name} {amount_formatted}.")

    # Edit the message, trapping any duplicate click "Message is not modified" exceptions
    try:
        await query.edit_message_text(
            text=reply_text, parse_mode="Markdown", reply_markup=reply_markup
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise
