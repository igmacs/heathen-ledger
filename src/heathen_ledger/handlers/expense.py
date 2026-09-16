import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from ..models import Expense
from .. import crud
from ..parser import (
    parse_pay_message,
    parse_payback_message,
)
from ..formatters import generate_expense_reply_text, format_cents
from ..services import expense_service
from ..services.exceptions import (
    UserNotFoundError,
    ValidationError,
    PermissionDeniedError,
)
from .voice import process_voice_audio
from .common import send_response

logger = logging.getLogger(__name__)


def build_expense_keyboard(
    expense: Expense, group_members: list, creator_id: int
) -> InlineKeyboardMarkup:
    """Build the inline keyboard with toggle buttons for each group member and an Undo button."""
    participant_ids = {s.user_id for s in expense.splits}

    # Sort members by first_name for UI consistency
    sorted_members = sorted(group_members, key=lambda m: m.first_name)

    keyboard = []
    row = []
    for member in sorted_members:
        is_p = member.id in participant_ids
        prefix = "✅" if is_p else "❌"
        button = InlineKeyboardButton(
            text=f"{prefix} {member.first_name}",
            callback_data=f"pay_toggle:{expense.id}:{member.id}:{creator_id}",
        )
        row.append(button)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    # Undo button below
    keyboard.append(
        [
            InlineKeyboardButton(
                text="🗑️ Undo",
                callback_data=f"undo:expense:{expense.id}:{creator_id}",
            )
        ]
    )
    return InlineKeyboardMarkup(keyboard)


@with_db_session
async def pay_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /pay command to record an expense."""
    if not update.message or not update.message.text:
        return

    # If replying to a voice/audio note with /pay (no arguments), delegate to voice interpretation
    reply_to = update.message.reply_to_message
    if reply_to and (reply_to.voice or reply_to.audio):
        text_clean = update.message.text.strip().lower()
        bot_username = getattr(context.bot, "username", None) or ""
        valid_commands = ["/pay"]
        if bot_username:
            valid_commands.append(f"/pay@{bot_username.lower()}")
        if text_clean in valid_commands:
            chat_id = update.effective_chat.id if update.effective_chat else None
            return await process_voice_audio(
                media_message=reply_to,
                response_message=update.message,
                context=context,
                session=session,
                chat_id=chat_id,
            )

    parsed = parse_pay_message(update.message.text)
    if "error" in parsed:
        keyboard = [[InlineKeyboardButton(text="OK", callback_data="dismiss")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_response(
            update,
            context,
            f"⚠️ Error parsing command: {parsed['error']}\n"
            f"Usage: `/pay <amount> [for <description>] [by <payer(s)>] [split <participants>] [on <date>]`",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return

    # Get active group
    group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
    if not group:
        group = crud.get_or_create_group(
            session, update.effective_chat.id, update.effective_chat.title
        )

    # Resolve sender
    sender = crud.get_user_by_telegram_id(session, update.effective_user.id)
    if not sender:
        sender = crud.get_or_create_user(
            session,
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name,
        )
    crud.add_user_to_group(session, sender, group)

    try:
        expense = expense_service.record_expense(
            session=session,
            group=group,
            sender=sender,
            command=parsed,
        )
    except (UserNotFoundError, ValidationError) as e:
        await send_response(update, context, f"⚠️ {e}")
        return

    creator_id = sender.id
    reply_text = generate_expense_reply_text(expense)
    reply_markup = build_expense_keyboard(expense, group.members, creator_id)

    await send_response(
        update, context, reply_text, parse_mode="Markdown", reply_markup=reply_markup
    )


@with_db_session
async def pay_toggle_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle toggling participants in an expense split."""
    query = update.callback_query
    if not query or not query.data:
        return

    # Callback data schema: pay_toggle:<expense_id>:<user_id>:<creator_id>
    parts = query.data.split(":")
    if len(parts) != 4:
        return

    _, expense_id_str, user_id_str, creator_id_str = parts
    expense_id = int(expense_id_str)
    target_user_id = int(user_id_str)
    creator_id = int(creator_id_str)

    # 1. Resolve clicking user's database ID
    clicker = crud.get_user_by_telegram_id(session, query.from_user.id)
    if not clicker:
        clicker = crud.get_or_create_user(
            session,
            query.from_user.id,
            query.from_user.username,
            query.from_user.first_name,
        )

    try:
        expense = expense_service.toggle_split_participant(
            session=session,
            expense_id=expense_id,
            target_user_id=target_user_id,
            clicking_user=clicker,
            creator_id=creator_id,
        )
    except PermissionDeniedError as e:
        await query.answer(text=f"⚠️ {e}", show_alert=True)
        return
    except ValidationError as e:
        await query.answer(text=f"⚠️ {e}", show_alert=True)
        if "not found" in str(e).lower():
            try:
                await query.edit_message_text(
                    text="⚠️ This expense has already been deleted or is not found.",
                    reply_markup=None,
                )
            except BadRequest as b_err:
                if "Message is not modified" not in str(b_err):
                    raise
        return

    # Refresh expense and get members to rebuild markup
    group = expense.group

    # 6. Re-generate response
    reply_text = generate_expense_reply_text(expense)
    reply_markup = build_expense_keyboard(expense, group.members, creator_id)

    try:
        await query.edit_message_text(
            text=reply_text,
            parse_mode="Markdown",
            reply_markup=reply_markup,
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

    await query.answer()


@with_db_session
async def payback_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /payback command to log direct payback transactions."""
    if not update.message or not update.message.text:
        return

    parsed = parse_payback_message(update.message.text)
    if "error" in parsed:
        keyboard = [[InlineKeyboardButton(text="OK", callback_data="dismiss")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_response(
            update,
            context,
            f"⚠️ Error parsing command: {parsed['error']}\n"
            f"Usage: `/payback [@payer] @recipient <amount>`",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return

    # Get active group
    group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
    if not group:
        group = crud.get_or_create_group(
            session, update.effective_chat.id, update.effective_chat.title
        )

    # Resolve sender
    sender = crud.get_user_by_telegram_id(session, update.effective_user.id)
    if not sender:
        sender = crud.get_or_create_user(
            session,
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name,
        )
    crud.add_user_to_group(session, sender, group)

    try:
        payment = expense_service.record_payback(
            session=session,
            group=group,
            sender=sender,
            command=parsed,
        )
    except UserNotFoundError as e:
        await send_response(update, context, f"⚠️ {e}")
        return

    amount_formatted = format_cents(payment.amount)
    creator_id = sender.id

    keyboard = [
        [
            InlineKeyboardButton(
                text="🗑️ Undo",
                callback_data=f"undo:payment:{payment.id}:{creator_id}",
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await send_response(
        update,
        context,
        f"✅ **Recorded payment:**\n"
        f"• **Paid by:** {payment.payer.first_name}\n"
        f"• **Paid to:** {payment.payee.first_name}\n"
        f"• **Amount:** {amount_formatted}",
        parse_mode="Markdown",
        reply_markup=reply_markup,
    )


@with_db_session
async def undo_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle CallbackQuery for transaction undo actions."""
    query = update.callback_query
    if not query or not query.data:
        return

    # Callback data schema: undo:<type>:<tx_id>:<creator_id>
    parts = query.data.split(":")
    if len(parts) != 4:
        return

    _, tx_type, tx_id_str, creator_id_str = parts
    tx_id = int(tx_id_str)
    creator_id = int(creator_id_str)

    # Resolve clicking user's database ID
    clicker = crud.get_user_by_telegram_id(session, query.from_user.id)
    if not clicker:
        # Fallback to auto-register them
        clicker = crud.get_or_create_user(
            session,
            query.from_user.id,
            query.from_user.username,
            query.from_user.first_name,
        )

    try:
        audit_desc = expense_service.undo_transaction(
            session=session,
            tx_type=tx_type,
            tx_id=tx_id,
            clicking_user=clicker,
            creator_id=creator_id,
        )
    except PermissionDeniedError as e:
        await query.answer(text=f"⚠️ {e}", show_alert=True)
        return
    except ValidationError as e:
        await query.answer(text=f"⚠️ {e}", show_alert=True)
        try:
            await query.edit_message_text(
                text="⚠️ This transaction has already been deleted or is not found.",
                reply_markup=None,
            )
        except BadRequest as b_err:
            if "Message is not modified" not in str(b_err):
                raise
        return

    # Log successful undo
    await query.answer(text="Transaction undone.")

    # Edit message to record undo audit log and remove keyboard
    undo_text = f"🗑️ **{audit_desc}** has been undone by {clicker.first_name}."
    try:
        await query.edit_message_text(
            text=undo_text,
            parse_mode="Markdown",
            reply_markup=None,
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise
