import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from ..models import User, Expense, Payment
from .. import crud
from ..parser import (
    parse_pay_message,
    split_amount_equally,
    parse_payback_message,
)

logger = logging.getLogger(__name__)


@with_db_session
async def pay_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Handle the /pay command to record an expense."""
    if not update.message or not update.message.text:
        return

    parsed = parse_pay_message(update.message.text)
    if "error" in parsed:
        keyboard = [[InlineKeyboardButton(text="OK", callback_data="dismiss")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚠️ Error parsing command: {parsed['error']}\n"
            f"Usage: `/pay [@payer] <amount> [for <description/participants>]`",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return

    amount = parsed["amount"]
    payer_username = parsed["payer_username"]
    participant_usernames = parsed["participants"]
    description = parsed["description"]

    # 1. Resolve Payer
    if payer_username:
        # Find payer in database by username
        payer = session.query(User).filter(User.username == payer_username).first()
        if not payer:
            await update.message.reply_text(
                f"⚠️ I don't know who @{payer_username} is yet! "
                f"They need to send a message in this group first so I can register them."
            )
            return
    else:
        # Default to the sender of the message
        payer = crud.get_user_by_telegram_id(session, update.effective_user.id)
        if not payer:
            # Fallback in case of registration delay
            payer = crud.get_or_create_user(
                session,
                update.effective_user.id,
                update.effective_user.username,
                update.effective_user.first_name,
            )

    # Get active group
    group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
    if not group:
        group = crud.get_or_create_group(
            session, update.effective_chat.id, update.effective_chat.title
        )

    # 2. Resolve Participants
    participants = []
    if participant_usernames:
        for username in participant_usernames:
            user = session.query(User).filter(User.username == username).first()
            if not user:
                await update.message.reply_text(
                    f"⚠️ I don't know who @{username} is yet! "
                    f"They need to send a message in this group first so I can register them."
                )
                return
            # Ensure participant is registered in the group members list
            crud.add_user_to_group(session, user, group)
            participants.append(user)
    else:
        # Default split: among all members registered in this group chat
        participants = group.members

    if not participants:
        await update.message.reply_text(
            "⚠️ No participants found to split the expense with."
        )
        return

    # 3. Calculate splits
    num_people = len(participants)
    shares = split_amount_equally(amount, num_people)

    # Map user ID to their split share amount
    splits_dict = {}
    for user, share in zip(participants, shares):
        splits_dict[user.id] = share

    # 4. Create the expense in database
    expense = crud.create_expense(
        session=session,
        group_id=group.id,
        payer_id=payer.id,
        amount=amount,
        description=description,
        splits=splits_dict,
    )

    # 5. Format and send response
    amount_formatted = f"{amount / 100:.2f}"
    parts_str = ", ".join([u.first_name for u in participants])
    desc_str = f" for '{description}'" if description else ""

    reply_text = (
        f"✅ Recorded expense:\n"
        f"• **Paid by:** {payer.first_name}\n"
        f"• **Amount:** ${amount_formatted}{desc_str}\n"
        f"• **Split between:** {parts_str}\n"
    )

    if num_people > 1:
        reply_text += "• **Shares:**\n"
        for user, share in zip(participants, shares):
            reply_text += f"  - {user.first_name}: ${share / 100:.2f}\n"

    # Get creator info
    creator = crud.get_user_by_telegram_id(session, update.effective_user.id)
    if not creator:
        creator = crud.get_or_create_user(
            session,
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name,
        )

    keyboard = [
        [
            InlineKeyboardButton(
                text="🗑️ Undo",
                callback_data=f"undo:expense:{expense.id}:{creator.id}",
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        reply_text, parse_mode="Markdown", reply_markup=reply_markup
    )


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
        await update.message.reply_text(
            f"⚠️ Error parsing command: {parsed['error']}\n"
            f"Usage: `/payback [@payer] @recipient <amount>`",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return

    amount = parsed["amount"]
    payer_username = parsed["payer_username"]
    payee_username = parsed["payee_username"]

    # Get active group
    group = crud.get_group_by_telegram_id(session, update.effective_chat.id)
    if not group:
        group = crud.get_or_create_group(
            session, update.effective_chat.id, update.effective_chat.title
        )

    # 1. Resolve Payer
    if payer_username:
        payer = session.query(User).filter(User.username == payer_username).first()
        if not payer:
            await update.message.reply_text(
                f"⚠️ I don't know who @{payer_username} is yet! "
                f"They need to send a message in this group first so I can register them."
            )
            return
    else:
        # Default to the sender of the message
        payer = crud.get_user_by_telegram_id(session, update.effective_user.id)
        if not payer:
            payer = crud.get_or_create_user(
                session,
                update.effective_user.id,
                update.effective_user.username,
                update.effective_user.first_name,
            )

    # 2. Resolve Payee
    payee = session.query(User).filter(User.username == payee_username).first()
    if not payee:
        await update.message.reply_text(
            f"⚠️ I don't know who @{payee_username} is yet! "
            f"They need to send a message in this group first so I can register them."
        )
        return

    # Ensure members are registered to the group members list
    crud.add_user_to_group(session, payer, group)
    crud.add_user_to_group(session, payee, group)

    # 3. Create direct payment in the database
    payment = crud.create_payment(
        session=session,
        group_id=group.id,
        payer_id=payer.id,
        payee_id=payee.id,
        amount=amount,
    )

    # 4. Format and reply
    amount_formatted = f"{amount / 100:.2f}"

    # Get creator info
    creator = crud.get_user_by_telegram_id(session, update.effective_user.id)
    if not creator:
        creator = crud.get_or_create_user(
            session,
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name,
        )

    keyboard = [
        [
            InlineKeyboardButton(
                text="🗑️ Undo",
                callback_data=f"undo:payment:{payment.id}:{creator.id}",
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ **Recorded payment:**\n"
        f"• **Paid by:** {payer.first_name}\n"
        f"• **Paid to:** {payee.first_name}\n"
        f"• **Amount:** ${amount_formatted}",
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

    # Security check: only the user who recorded the transaction can undo it
    if clicker.id != creator_id:
        creator_user = session.query(User).filter(User.id == creator_id).first()
        creator_name = (
            creator_user.first_name if creator_user else "the user who recorded it"
        )
        await query.answer(
            text=f"⚠️ Only {creator_name} can undo this transaction.",
            show_alert=True,
        )
        return

    # Perform the deletion
    success = False
    audit_desc = ""
    if tx_type == "expense":
        expense = session.query(Expense).filter(Expense.id == tx_id).first()
        if expense:
            amount_formatted = f"${expense.amount / 100:.2f}"
            desc_str = f" for '{expense.description}'" if expense.description else ""
            audit_desc = f"Recorded expense of {amount_formatted}{desc_str}"
            success = crud.delete_expense(session, tx_id)
    elif tx_type == "payment":
        payment = session.query(Payment).filter(Payment.id == tx_id).first()
        if payment:
            amount_formatted = f"${payment.amount / 100:.2f}"
            audit_desc = f"Recorded payment of {amount_formatted}"
            success = crud.delete_payment(session, tx_id)

    if not success:
        await query.answer(
            text="⚠️ Transaction not found or already deleted.", show_alert=True
        )
        try:
            await query.edit_message_text(
                text="⚠️ This transaction has already been deleted or is not found.",
                reply_markup=None,
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
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
