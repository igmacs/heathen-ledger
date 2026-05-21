import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from ..models import Expense, Payment
from .. import crud
from ..parser import generate_history_summary

logger = logging.getLogger(__name__)


async def refresh_history_message(query, session: Session):
    """Helper to refresh the history message with updated transactions."""
    group = crud.get_group_by_telegram_id(session, query.message.chat.id)
    if not group:
        try:
            await query.edit_message_text(
                text="ℹ️ No transactions or members recorded for this group yet.",
                reply_markup=None,
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        return

    # Fetch last 10 transactions
    txs = crud.get_recent_transactions(session, group.id, limit=10)
    reply_text = generate_history_summary(txs)

    keyboard = []
    if txs:
        for i, tx in enumerate(txs, 1):
            t_type = tx["type"]
            obj = tx["obj"]
            callback_data = f"hist_del:{t_type}:{obj.id}"
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=f"🗑️ Delete {i}", callback_data=callback_data
                    )
                ]
            )

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    try:
        await query.edit_message_text(
            text=reply_text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise


@with_db_session
async def history_delete_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle callback query when a history entry delete button is clicked."""
    query = update.callback_query
    if not query or not query.data:
        return

    # Callback data schema: hist_del:<type>:<tx_id>
    parts = query.data.split(":")
    if len(parts) != 3:
        return

    t_type = parts[1]
    try:
        tx_id = int(parts[2])
    except ValueError:
        return

    if not query.message or not query.message.chat:
        return

    # Fetch clicking user
    clicker = crud.get_user_by_telegram_id(session, query.from_user.id)
    if not clicker:
        # Fallback to auto-register them
        clicker = crud.get_or_create_user(
            session,
            query.from_user.id,
            query.from_user.username,
            query.from_user.first_name,
        )

    # Fetch transaction to authorize and delete
    if t_type == "expense":
        expense = session.query(Expense).filter(Expense.id == tx_id).first()
        if not expense:
            await query.answer(
                text="⚠️ Expense not found or already deleted.", show_alert=True
            )
            await refresh_history_message(query, session)
            return

        # Security check: only the payer can delete the expense
        if clicker.id != expense.payer_id:
            payer_name = expense.payer.first_name if expense.payer else "the payer"
            await query.answer(
                text=f"⚠️ Only {payer_name} can delete this expense.",
                show_alert=True,
            )
            return

        crud.delete_expense(session, tx_id)
        await query.answer(text="Expense deleted.")

    elif t_type == "payment":
        payment = session.query(Payment).filter(Payment.id == tx_id).first()
        if not payment:
            await query.answer(
                text="⚠️ Payment not found or already deleted.", show_alert=True
            )
            await refresh_history_message(query, session)
            return

        # Security check: only the payer or payee can delete the payment
        if clicker.id not in (payment.payer_id, payment.payee_id):
            payer_name = payment.payer.first_name if payment.payer else "the payer"
            payee_name = payment.payee.first_name if payment.payee else "the payee"
            await query.answer(
                text=f"⚠️ Only {payer_name} or {payee_name} can delete this payment.",
                show_alert=True,
            )
            return

        crud.delete_payment(session, tx_id)
        await query.answer(text="Payment deleted.")

    # Refresh history message
    await refresh_history_message(query, session)


@with_db_session
async def history_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /history command to show recent transactions."""
    if not update.effective_chat:
        return

    group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
    if not group:
        await update.message.reply_text(
            "ℹ️ No transactions or members recorded for this group yet."
        )
        return

    # Fetch last 10 transactions
    txs = crud.get_recent_transactions(session, group.id, limit=10)
    reply_text = generate_history_summary(txs)

    keyboard = []
    if txs:
        for i, tx in enumerate(txs, 1):
            t_type = tx["type"]
            obj = tx["obj"]
            callback_data = f"hist_del:{t_type}:{obj.id}"
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=f"🗑️ Delete {i}", callback_data=callback_data
                    )
                ]
            )

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(
        reply_text, parse_mode="Markdown", reply_markup=reply_markup
    )
