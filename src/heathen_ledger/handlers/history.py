"""Handlers for viewing recent transaction history and interactive deletion."""

import logging

from sqlalchemy.orm import Session
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..database import with_db_session
from ..formatters import generate_history_rich_html
from ..repositories import GroupRepository, UserRepository
from ..services import HistoryService
from ..services.exceptions import PermissionDeniedError, ValidationError
from ..telegram import TelegramRichClient
from .common import require_group_chat, send_response

logger = logging.getLogger(__name__)


async def refresh_history_message(
    query, session: Session, context: ContextTypes.DEFAULT_TYPE | None = None
):
    """Helper to refresh the history message with updated transactions using Rich Messages."""
    bot = getattr(context, "bot", None) if context else None
    group = GroupRepository(session).get_by_telegram_id(query.message.chat.id)
    if not group:
        await TelegramRichClient.edit_rich_message_or_ephemeral(
            query=query,
            bot=bot,
            rich_html="<p>ℹ️ No transactions or members recorded for this group yet.</p>",
            reply_markup=None,
        )
        return

    txs = HistoryService.get_recent_transactions(session, group.id, limit=10)
    rich_html = generate_history_rich_html(txs)

    # Retain action buttons (Share to group / Dismiss) if present, ignoring bottom delete buttons
    msg = getattr(query, "message", None)
    orig_reply_markup = getattr(msg, "reply_markup", None)
    action_markup = None
    if orig_reply_markup and hasattr(orig_reply_markup, "inline_keyboard"):
        action_rows = []
        for row in orig_reply_markup.inline_keyboard:
            action_row = [
                btn
                for btn in row
                if getattr(btn, "callback_data", "")
                and (
                    btn.callback_data.startswith("persist:")
                    or btn.callback_data.startswith("dismiss")
                )
            ]
            if action_row:
                action_rows.append(action_row)
        if action_rows:
            action_markup = InlineKeyboardMarkup(action_rows)

    await TelegramRichClient.edit_rich_message_or_ephemeral(
        query=query,
        bot=bot,
        rich_html=rich_html,
        reply_markup=action_markup,
    )


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

    # Resolve clicking user (guaranteed registered by group=-1 auto_register)
    clicker = UserRepository(session).get_by_telegram_id(query.from_user.id)
    if not clicker:
        return

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
        await refresh_history_message(query, session, context)
        return

    # Refresh history message
    await refresh_history_message(query, session, context)


@require_group_chat
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
            rich_html="<p>ℹ️ No transactions or members recorded for this group yet.</p>",
        )
        return

    # Fetch last 10 transactions
    txs = HistoryService.get_recent_transactions(session, group.id, limit=10)
    rich_html = generate_history_rich_html(txs)
    await send_response(
        update,
        context,
        rich_html=rich_html,
        reply_markup=None,
    )
