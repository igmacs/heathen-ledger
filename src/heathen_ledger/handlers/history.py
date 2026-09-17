"""Handlers for viewing recent transaction history and interactive deletion."""

import logging
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from ..repositories import GroupRepository
from ..services import HistoryService, MemberRegistrationService
from ..services.exceptions import PermissionDeniedError, ValidationError
from ..formatters import generate_history_summary
from ..keyboards import HistoryKeyboardBuilder
from .common import send_response

logger = logging.getLogger(__name__)


async def refresh_history_message(query, session: Session):
    """Helper to refresh the history message with updated transactions."""
    group = GroupRepository(session).get_by_telegram_id(query.message.chat.id)
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

    txs = HistoryService.get_recent_transactions(session, group.id, limit=10)
    reply_text = generate_history_summary(txs)
    reply_markup = HistoryKeyboardBuilder.build_history_keyboard(txs)
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

    clicker, _ = MemberRegistrationService.ensure_member_in_group(
        session=session,
        chat_id=query.message.chat.id,
        user_id=query.from_user.id,
        username=query.from_user.username,
        first_name=query.from_user.first_name,
    )

    try:
        msg = HistoryService.delete_transaction(
            session=session,
            tx_type=t_type,
            tx_id=tx_id,
            clicking_user=clicker,
        )
        await query.answer(text=msg)
    except PermissionDeniedError as e:
        await query.answer(text=f"⚠️ {e}", show_alert=True)
        return
    except ValidationError as e:
        await query.answer(text=f"⚠️ {e}", show_alert=True)
        await refresh_history_message(query, session)
        return

    # Refresh history message
    await refresh_history_message(query, session)


@with_db_session
async def history_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /history command to show recent transactions."""
    if not update.effective_chat:
        return

    group = GroupRepository(session).get_by_telegram_id(update.effective_chat.id)
    if not group:
        await send_response(
            update,
            context,
            "ℹ️ No transactions or members recorded for this group yet.",
        )
        return

    # Fetch last 10 transactions
    txs = HistoryService.get_recent_transactions(session, group.id, limit=10)
    reply_text = generate_history_summary(txs)
    reply_markup = HistoryKeyboardBuilder.build_history_keyboard(txs)
    await send_response(
        update,
        context,
        reply_text,
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )
