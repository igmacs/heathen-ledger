import logging

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from ..database import with_db_session
from ..formatters import format_cents, generate_expense_reply_text
from ..keyboards import ExpenseKeyboardBuilder
from ..parser import (
    parse_pay_message,
    parse_payback_message,
)
from ..repositories import UserRepository
from ..services import ExpenseService, MemberRegistrationService
from ..services.exceptions import (
    PermissionDeniedError,
    UserNotFoundError,
    ValidationError,
)
from .common import require_group_chat, send_response
from .voice import process_voice_audio

logger = logging.getLogger(__name__)

# Backward-compatible aliases for existing callers/tests
build_expense_undo_keyboard = ExpenseKeyboardBuilder.build_expense_undo_keyboard


@require_group_chat
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

    # Ensure sender and group exist and are linked
    sender, group = MemberRegistrationService.ensure_member_in_group(
        session=session,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name or "",
        chat_title=update.effective_chat.title,
    )

    try:
        expense = ExpenseService.record_expense(
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
    reply_markup = ExpenseKeyboardBuilder.build_expense_undo_keyboard(
        expense_id=expense.id, creator_id=creator_id
    )

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

    # Resolve clicking user (guaranteed registered by group=-1 auto_register)
    clicker = UserRepository(session).get_by_telegram_id(query.from_user.id)
    if not clicker:
        return

    try:
        expense = ExpenseService.toggle_split_participant(
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

    # Re-generate response
    reply_text = generate_expense_reply_text(expense)
    reply_markup = ExpenseKeyboardBuilder.build_split_toggle_keyboard(
        expense=expense, group_members=group.members, creator_id=creator_id
    )

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


@require_group_chat
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

    # Ensure sender and group exist and are linked
    sender, group = MemberRegistrationService.ensure_member_in_group(
        session=session,
        chat_id=update.effective_chat.id,
        user_id=update.effective_user.id,
        username=update.effective_user.username,
        first_name=update.effective_user.first_name or "",
        chat_title=update.effective_chat.title,
    )

    try:
        payment = ExpenseService.record_payback(
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

    reply_markup = ExpenseKeyboardBuilder.build_payback_undo_keyboard(
        payment.id, creator_id
    )

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

    # Resolve clicking user (guaranteed registered by group=-1 auto_register)
    clicker = UserRepository(session).get_by_telegram_id(query.from_user.id)
    if not clicker:
        return

    try:
        audit_desc = ExpenseService.undo_transaction(
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
