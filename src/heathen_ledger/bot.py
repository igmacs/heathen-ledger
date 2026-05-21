import os
import logging
from dotenv import load_dotenv
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from sqlalchemy.orm import Session
from .database import with_db_session
from .models import User, Expense, Payment
from . import crud
from .parser import (
    parse_pay_message,
    split_amount_equally,
    generate_balances_summary,
    simplify_debts,
    generate_settlements_summary,
    parse_payback_message,
    generate_history_summary,
)

load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


@with_db_session
async def auto_register(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """Automatically register the user and group chat if they don't exist yet."""
    if not update.effective_chat or not update.effective_user:
        return

    # Skip bots
    if update.effective_user.is_bot:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name
    title = update.effective_chat.title or f"Private Chat ({user_id})"

    db_user = crud.get_or_create_user(session, user_id, username, first_name)
    db_group = crud.get_or_create_group(session, chat_id, title)
    crud.add_user_to_group(session, db_user, db_group)


@with_db_session
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session):
    """Send a message when the command /start is issued."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "👋 **Hello! I am Heathen Ledger.**\n\n"
            '_*"This group deserves a better class of ledger, and I’m gonna give it to ‘em."*_\n\n'
            "I help you track and settle shared expenses in group chats. Type /help to see all available commands."
        ),
        parse_mode="Markdown",
    )


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

    balances = crud.get_group_balances(session, group.id)
    users_by_id = {u.id: u for u in group.members}

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

    balances = crud.get_group_balances(session, group.id)
    transactions = simplify_debts(balances)
    users_by_id = {u.id: u for u in group.members}

    reply_text = generate_settlements_summary(transactions, users_by_id)

    reply_markup = None
    if transactions:
        keyboard = []
        for tx in transactions:
            from_db_user = users_by_id.get(tx["from_user_id"])
            to_db_user = users_by_id.get(tx["to_user_id"])
            from_name = (
                from_db_user.first_name
                if from_db_user
                else f"User {tx['from_user_id']}"
            )
            to_name = (
                to_db_user.first_name if to_db_user else f"User {tx['to_user_id']}"
            )
            amount_formatted = f"${tx['amount'] / 100:.2f}"

            button_text = f"✅ {from_name} paid {to_name} {amount_formatted}"
            callback_data = (
                f"settle:{tx['from_user_id']}:{tx['to_user_id']}:{tx['amount']}"
            )
            keyboard.append(
                [InlineKeyboardButton(text=button_text, callback_data=callback_data)]
            )
        reply_markup = InlineKeyboardMarkup(keyboard)

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

    if clicking_user.id not in (from_id, to_id):
        # Retrieve names of the parties for a descriptive alert
        from_db_user = session.query(User).filter(User.id == from_id).first()
        to_db_user = session.query(User).filter(User.id == to_id).first()
        from_name = from_db_user.first_name if from_db_user else "the debtor"
        to_name = to_db_user.first_name if to_db_user else "the creditor"
        await query.answer(
            text=f"⚠️ Only {from_name} or {to_name} can confirm this payment.",
            show_alert=True,
        )
        return

    # Record the payment
    crud.create_payment(
        session=session,
        group_id=group.id,
        payer_id=from_id,
        payee_id=to_id,
        amount=amount,
    )

    # Re-calculate balances and settlements
    balances = crud.get_group_balances(session, group.id)
    transactions = simplify_debts(balances)
    users_by_id = {u.id: u for u in group.members}

    reply_text = generate_settlements_summary(transactions, users_by_id)

    reply_markup = None
    if transactions:
        keyboard = []
        for tx in transactions:
            from_db_user = users_by_id.get(tx["from_user_id"])
            to_db_user = users_by_id.get(tx["to_user_id"])
            from_name = (
                from_db_user.first_name
                if from_db_user
                else f"User {tx['from_user_id']}"
            )
            to_name = (
                to_db_user.first_name if to_db_user else f"User {tx['to_user_id']}"
            )
            amount_formatted = f"${tx['amount'] / 100:.2f}"

            button_text = f"✅ {from_name} paid {to_name} {amount_formatted}"
            callback_data = (
                f"settle:{tx['from_user_id']}:{tx['to_user_id']}:{tx['amount']}"
            )
            keyboard.append(
                [InlineKeyboardButton(text=button_text, callback_data=callback_data)]
            )
        reply_markup = InlineKeyboardMarkup(keyboard)

    # Inform Telegram that the callback was handled
    from_db_user = session.query(User).filter(User.id == from_id).first()
    to_db_user = session.query(User).filter(User.id == to_id).first()
    from_name = from_db_user.first_name if from_db_user else "Debtor"
    to_name = to_db_user.first_name if to_db_user else "Creditor"
    amount_formatted = f"${amount / 100:.2f}"
    await query.answer(text=f"Recorded: {from_name} paid {to_name} {amount_formatted}.")

    # Edit the message, trapping any duplicate click "Message is not modified" exceptions
    try:
        await query.edit_message_text(
            text=reply_text, parse_mode="Markdown", reply_markup=reply_markup
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise


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


async def dismiss_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback query when a dismiss/OK button is clicked to delete the message."""
    query = update.callback_query
    if not query:
        return

    if query.data != "dismiss":
        return

    try:
        await query.message.delete()
    except BadRequest as e:
        logging.warning(f"Failed to delete message: {e}")

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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command to display instructions and formatting."""
    help_text = (
        "📖 **Heathen Ledger Bot Help**\n\n"
        "Here are the available commands:\n\n"
        "💸 **Logging Expenses**\n"
        "• `/pay <amount> [for <description>]` — Log an expense paid by you, split equally among everyone. (e.g. `/pay 12.50 for Pizza`)\n"
        "• `/pay @payer <amount> [for <description>]` — Log an expense paid by another member, split equally. (e.g. `/pay @Alice 50 for Dinner`)\n"
        "• `/pay @payer <amount> for @user1 @user2 ...` — Log an expense split specifically among selected members. (e.g. `/pay @Alice 50 for @Bob @Charlie`)\n\n"
        "🤝 **Settle Debts & Paybacks**\n"
        "• `/balances` — View current net group balances (highest creditor to highest debtor).\n"
        "• `/settle` — Calculate the minimum payback transactions needed to settle all group debts.\n"
        "• `/payback @recipient <amount>` — Record a direct payment from you to settle up. (e.g. `/payback @Alice 10`)\n"
        "• `/payback @payer @recipient <amount>` — Record a direct payment between other group members. (e.g. `/payback @Bob @Alice 12.50`)\n\n"
        "📜 **History & Audit Logs**\n"
        "• `/history` — View the last 10 transactions logged in the group chat.\n\n"
        "⚠️ **User Registration:**\n"
        "The bot automatically registers users when they send a message. "
        "Before you can assign a payment/expense to a member, they *must have sent at least one message* in the group."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def post_init(application: Application) -> None:
    """Set the bot commands for autocompletion."""
    commands = [
        BotCommand("pay", "Log an expense split among members"),
        BotCommand("balances", "View current group balances"),
        BotCommand("settle", "Calculate payback transactions"),
        BotCommand("payback", "Record a direct payment"),
        BotCommand("history", "View last 10 transactions"),
        BotCommand("help", "Display help message"),
    ]
    await application.bot.set_my_commands(commands)


if __name__ == "__main__":
    # Fetch the token from the environment variable
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError(
            "No token provided. Please set the TELEGRAM_BOT_TOKEN environment variable."
        )

    application = ApplicationBuilder().token(token).post_init(post_init).build()

    # Add auto-registration handler in a separate group (-1) so it runs before command handlers (group 0)
    application.add_handler(MessageHandler(filters.ALL, auto_register), group=-1)

    start_handler = CommandHandler("start", start)
    pay_handler = CommandHandler("pay", pay_command)
    balances_handler = CommandHandler("balances", balances_command)
    settle_handler = CommandHandler("settle", settle_command)
    payback_handler = CommandHandler("payback", payback_command)
    history_handler = CommandHandler("history", history_command)
    help_handler = CommandHandler("help", help_command)
    settle_callback_handler_registered = CallbackQueryHandler(
        settle_callback_handler, pattern="^settle:"
    )
    undo_callback_handler_registered = CallbackQueryHandler(
        undo_callback_handler, pattern="^undo:"
    )
    hist_del_callback_handler_registered = CallbackQueryHandler(
        history_delete_callback_handler, pattern="^hist_del:"
    )
    dismiss_callback_handler_registered = CallbackQueryHandler(
        dismiss_callback_handler, pattern="^dismiss$"
    )

    application.add_handler(start_handler)
    application.add_handler(pay_handler)
    application.add_handler(balances_handler)
    application.add_handler(settle_handler)
    application.add_handler(payback_handler)
    application.add_handler(history_handler)
    application.add_handler(help_handler)
    application.add_handler(settle_callback_handler_registered)
    application.add_handler(undo_callback_handler_registered)
    application.add_handler(hist_del_callback_handler_registered)
    application.add_handler(dismiss_callback_handler_registered)

    # Run the bot until the user presses Ctrl-C
    application.run_polling()
