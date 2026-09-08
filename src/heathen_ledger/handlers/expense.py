import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from ..models import User, Expense, Payment, ExpenseSplit
from .. import crud
from ..parser import (
    parse_pay_message,
    split_amount_equally,
    parse_payback_message,
)
from .voice import process_voice_audio

logger = logging.getLogger(__name__)


def generate_expense_reply_text(expense: Expense) -> str:
    """Format the expense split summary."""
    amount_formatted = f"{expense.amount / 100:.2f}"
    desc_str = f" for '{expense.description}'" if expense.description else ""

    # Sort the splits by the user's first_name to keep the display order stable
    sorted_splits = sorted(expense.splits, key=lambda s: s.user.first_name)
    participants = [s.user for s in sorted_splits]
    parts_str = ", ".join([u.first_name for u in participants])

    # Format Payers
    if expense.payers and len(expense.payers) > 1:
        payer_lines = []
        for p in expense.payers:
            payer_lines.append(f"  - {p.user.first_name}: ${p.amount / 100:.2f}")
        paid_by_str = "• **Paid by:**\n" + "\n".join(payer_lines)
    elif expense.payers and len(expense.payers) == 1:
        paid_by_str = f"• **Paid by:** {expense.payers[0].user.first_name}"
    elif expense.payer:
        paid_by_str = f"• **Paid by:** {expense.payer.first_name}"
    else:
        paid_by_str = f"• **Paid by:** User {expense.payer_id}"

    date_line = (
        f"• **Date:** {expense.expense_date.isoformat()}\n"
        if expense.expense_date
        else ""
    )

    reply_text = (
        f"✅ Recorded expense:\n"
        f"{paid_by_str}\n"
        f"• **Amount:** ${amount_formatted}{desc_str}\n"
        f"{date_line}"
        f"• **Split between:** {parts_str}\n"
    )

    if len(sorted_splits) > 1:
        reply_text += "• **Shares:**\n"
        for s in sorted_splits:
            reply_text += f"  - {s.user.first_name}: ${s.amount / 100:.2f}\n"

    return reply_text


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
        await update.message.reply_text(
            f"⚠️ Error parsing command: {parsed['error']}\n"
            f"Usage: `/pay <amount> [for <description>] [by <payer(s)>] [split <participants>] [on <date>]`",
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        return

    amount = parsed["amount"]
    raw_payers = parsed.get("payers", {})
    description = parsed.get("description")
    split_spec = parsed.get("split_spec", {"mode": "all", "participants": []})
    expense_date = parsed.get("expense_date")

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

    # 1. Resolve Payers
    payers_dict = {}
    for uname, p_cents in raw_payers.items():
        if uname == "me":
            u = sender
        else:
            u = session.query(User).filter(User.username == uname).first()
            if not u:
                await update.message.reply_text(
                    f"⚠️ I don't know who @{uname} is yet! "
                    f"They need to send a message in this group first so I can register them."
                )
                return
        crud.add_user_to_group(session, u, group)
        payers_dict[u.id] = p_cents

    # 2. Resolve Participants and Splits
    split_mode = split_spec.get("mode", "all")
    splits_dict = {}

    if split_mode == "all":
        participants = group.members
        if not participants:
            await update.message.reply_text(
                "⚠️ No participants found to split the expense with."
            )
            return
        shares = split_amount_equally(amount, len(participants))
        for u, s in zip(participants, shares):
            splits_dict[u.id] = s

    elif split_mode == "except":
        excluded = set(split_spec.get("excluded", []))
        participants = [
            m for m in group.members if (m.username or "").lower() not in excluded
        ]
        if not participants:
            await update.message.reply_text(
                "⚠️ No participants left to split the expense with after exclusions."
            )
            return
        shares = split_amount_equally(amount, len(participants))
        for u, s in zip(participants, shares):
            splits_dict[u.id] = s

    elif split_mode == "subset":
        participants = []
        for uname in split_spec.get("participants", []):
            if uname == "me":
                u = sender
            else:
                u = session.query(User).filter(User.username == uname).first()
                if not u:
                    await update.message.reply_text(
                        f"⚠️ I don't know who @{uname} is yet! "
                        f"They need to send a message in this group first so I can register them."
                    )
                    return
            crud.add_user_to_group(session, u, group)
            participants.append(u)

        if not participants:
            await update.message.reply_text(
                "⚠️ No participants found to split the expense with."
            )
            return
        shares = split_amount_equally(amount, len(participants))
        for u, s in zip(participants, shares):
            splits_dict[u.id] = s

    elif split_mode == "custom":
        for uname, share_cents in split_spec.get("shares", {}).items():
            if uname == "me":
                u = sender
            else:
                u = session.query(User).filter(User.username == uname).first()
                if not u:
                    await update.message.reply_text(
                        f"⚠️ I don't know who @{uname} is yet! "
                        f"They need to send a message in this group first so I can register them."
                    )
                    return
            crud.add_user_to_group(session, u, group)
            splits_dict[u.id] = share_cents

    # 3. Create the expense in database
    expense = crud.create_expense(
        session=session,
        group_id=group.id,
        amount=amount,
        description=description,
        splits=splits_dict,
        payers=payers_dict,
        expense_date=expense_date,
    )

    creator_id = sender.id
    reply_text = generate_expense_reply_text(expense)
    reply_markup = build_expense_keyboard(expense, group.members, creator_id)

    await update.message.reply_text(
        reply_text, parse_mode="Markdown", reply_markup=reply_markup
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

    # 2. Check permissions (only creator can toggle)
    if clicker.id != creator_id:
        creator_user = session.query(User).filter(User.id == creator_id).first()
        creator_name = (
            creator_user.first_name if creator_user else "the user who recorded it"
        )
        await query.answer(
            text=f"⚠️ Only {creator_name} can edit this split.",
            show_alert=True,
        )
        return

    # 3. Retrieve expense and group
    expense = session.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        await query.answer(
            text="⚠️ Expense not found or already deleted.", show_alert=True
        )
        try:
            await query.edit_message_text(
                text="⚠️ This expense has already been deleted or is not found.",
                reply_markup=None,
            )
        except BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        return

    # 4. Modify splits list
    current_splits = {s.user_id: s for s in expense.splits}
    if target_user_id in current_splits:
        # Prevent removing the last participant
        if len(current_splits) <= 1:
            await query.answer(
                text="⚠️ Cannot remove the last participant from the split.",
                show_alert=True,
            )
            return
        # Delete split
        session.delete(current_splits[target_user_id])
        current_splits.pop(target_user_id)
    else:
        # Add split
        new_split = ExpenseSplit(
            expense_id=expense.id, user_id=target_user_id, amount=0
        )
        session.add(new_split)
        current_splits[target_user_id] = new_split

    session.flush()

    # 5. Recalculate split shares
    num_people = len(current_splits)
    shares = split_amount_equally(expense.amount, num_people)
    # Map them to remaining users (sort them to ensure deterministic remainder distribution)
    sorted_remaining_ids = sorted(current_splits.keys())
    for user_id, share in zip(sorted_remaining_ids, shares):
        current_splits[user_id].amount = share

    session.commit()

    # Refresh expense and get members to rebuild markup
    session.refresh(expense)
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
