"""Handlers for balance inquiries, debt settlements, and interactive payback confirmations."""

import logging
from typing import List, Dict, Any, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from ..models import User
from .. import crud
from ..formatters import (
    generate_balances_summary,
    generate_settlements_summary,
    format_cents,
)
from ..services import settlement_service
from ..services.exceptions import PermissionDeniedError

logger = logging.getLogger(__name__)


def build_settle_keyboard(
    transactions: List[Dict[str, Any]], users_by_id: Dict[int, Any]
) -> Optional[InlineKeyboardMarkup]:
    """Build inline confirmation buttons for suggested payback transactions."""
    if not transactions:
        return None

    keyboard = []
    for tx in transactions:
        from_db_user = users_by_id.get(tx["from_user_id"])
        to_db_user = users_by_id.get(tx["to_user_id"])
        from_name = (
            from_db_user.first_name if from_db_user else f"User {tx['from_user_id']}"
        )
        to_name = to_db_user.first_name if to_db_user else f"User {tx['to_user_id']}"
        amount_formatted = format_cents(tx["amount"])

        button_text = f"✅ {from_name} paid {to_name} {amount_formatted}"
        callback_data = f"settle:{tx['from_user_id']}:{tx['to_user_id']}:{tx['amount']}"
        keyboard.append(
            [InlineKeyboardButton(text=button_text, callback_data=callback_data)]
        )
    return InlineKeyboardMarkup(keyboard)


@with_db_session
async def balances_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /balances command to show net group balances."""
    if not update.effective_chat:
        return

    group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
    if not group or not group.members:
        await update.message.reply_text(
            "ℹ️ No transactions or members recorded for this group yet."
        )
        return

    balances, _, users_by_id = settlement_service.get_group_balances_and_settlements(
        session, group.id
    )
    reply_text = generate_balances_summary(balances, users_by_id)
    await update.message.reply_text(reply_text, parse_mode="Markdown")


@with_db_session
async def settle_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /settle command to show simplified payback transactions."""
    if not update.effective_chat:
        return

    group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
    if not group or not group.members:
        await update.message.reply_text(
            "ℹ️ No transactions or members recorded for this group yet."
        )
        return

    _, transactions, users_by_id = (
        settlement_service.get_group_balances_and_settlements(session, group.id)
    )
    reply_text = generate_settlements_summary(transactions, users_by_id)
    reply_markup = build_settle_keyboard(transactions, users_by_id)

    await update.message.reply_text(
        reply_text, parse_mode="Markdown", reply_markup=reply_markup
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

    group = crud.get_group_by_telegram_id(session, query.message.chat.id)
    if not group:
        await query.answer(text="⚠️ Group not found in database.", show_alert=True)
        return

    # Security check: verify clicking user's role
    clicking_user = crud.get_user_by_telegram_id(session, query.from_user.id)
    if not clicking_user:
        await query.answer(
            text="⚠️ You are not registered in this group yet. Send a message first!",
            show_alert=True,
        )
        return

    try:
        settlement_service.record_settlement_payment(
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
    _, transactions, users_by_id = (
        settlement_service.get_group_balances_and_settlements(session, group.id)
    )
    reply_text = generate_settlements_summary(transactions, users_by_id)
    reply_markup = build_settle_keyboard(transactions, users_by_id)

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
