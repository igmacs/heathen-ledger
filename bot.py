import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

import database
import settlement

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

def get_user_identifier(user) -> str:
    """Gets a consistent string identifier for a user."""
    if user.username:
        return f"@{user.username}"
    return f"@{user.first_name}"

async def track_active_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passively listens to messages and tracks active users in the chat."""
    if not update.effective_chat or not update.message or not update.message.from_user:
        return
        
    chat_id = update.effective_chat.id
    user_identifier = get_user_identifier(update.message.from_user)
    
    # Track the user in the database
    database.track_user(chat_id, user_identifier)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    chat_id = update.effective_chat.id
    user_identifier = get_user_identifier(update.message.from_user)
    database.track_user(chat_id, user_identifier)
    
    await context.bot.send_message(
        chat_id=chat_id, 
        text="Hello! I am Heathen Ledger. Add me to a group to track expenses. Use /pay, /balances, and /settle."
    )

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /pay command."""
    chat_id = update.effective_chat.id
    sender_identifier = get_user_identifier(update.message.from_user)
    database.track_user(chat_id, sender_identifier)
    
    text = update.message.text
    
    # Regex to parse: /pay [@payer] [amount] [description including @participants]
    # Match 1: Optional Payer (e.g. @Alice)
    # Match 2: Amount (e.g. 50, 50.5)
    # Match 3: Rest of the text
    pattern = r"^\s*/pay(?:@[a-zA-Z0-9_]+)?\s+(?:(@\w+)\s+)?([\d\.]+)\s+(.*)$"
    match = re.match(pattern, text, re.IGNORECASE)
    
    if not match:
        await context.bot.send_message(
            chat_id=chat_id,
            text="Invalid format. Use: /pay [@payer] <amount> [description] [@participant1 @participant2...]"
        )
        return
        
    payer = match.group(1) if match.group(1) else sender_identifier
    try:
        amount = float(match.group(2))
    except ValueError:
        await context.bot.send_message(chat_id=chat_id, text="Invalid amount.")
        return
        
    rest_of_text = match.group(3)
    
    # Extract participants and description
    participants = []
    description_parts = []
    
    for word in rest_of_text.split():
        if word.startswith('@'):
            participants.append(word)
        elif word.lower() != 'for': # Skip 'for' if it's used as a separator
            description_parts.append(word)
            
    description = " ".join(description_parts)
    if not description:
        description = "Unknown expense"
        
    database.add_expense(chat_id, payer, amount, description, participants)
    
    split_msg = f"split specifically between {', '.join(participants)}" if participants else "split equally among everyone"
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Added expense: {payer} paid {amount:.2f} for '{description}' ({split_msg})."
    )

async def balances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /balances command."""
    chat_id = update.effective_chat.id
    bals = database.get_balances(chat_id)
    
    if not bals:
        await context.bot.send_message(chat_id=chat_id, text="No active balances in this group.")
        return
        
    lines = ["**Current Balances:**"]
    for user, amount in sorted(bals.items(), key=lambda x: x[1], reverse=True):
        if amount > 0:
            lines.append(f"{user} is owed {amount:.2f}")
        elif amount < 0:
            lines.append(f"{user} owes {-amount:.2f}")
            
    # Remove users with exactly 0.00
            
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode='Markdown')

async def settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /settle command."""
    chat_id = update.effective_chat.id
    bals = database.get_balances(chat_id)
    
    if not bals:
        await context.bot.send_message(chat_id=chat_id, text="No debts to settle!")
        return
        
    transactions = settlement.calculate_settlements(bals)
    
    if not transactions:
        await context.bot.send_message(chat_id=chat_id, text="Everyone is settled up!")
        return
        
    lines = ["**How to settle up:**"]
    for debtor, creditor, amount in transactions:
        lines.append(f"💸 {debtor} should pay {creditor} **{amount:.2f}**")
        
    lines.append("\nOnce everyone has paid, use `/clear` to reset the ledger.")
    
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode='Markdown')

async def clear_ledger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /clear command to wipe debts."""
    chat_id = update.effective_chat.id
    database.clear_expenses(chat_id)
    await context.bot.send_message(chat_id=chat_id, text="Ledger cleared! All debts have been wiped.")

def main():
    # Initialize DB
    database.init_db()

    # Fetch the token from the environment variable
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("No token provided. Please set the TELEGRAM_BOT_TOKEN environment variable.")

    application = ApplicationBuilder().token(token).build()

    # Commands
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('pay', pay))
    application.add_handler(CommandHandler('balances', balances))
    application.add_handler(CommandHandler('settle', settle))
    application.add_handler(CommandHandler('clear', clear_ledger))
    
    # Message handler to passively track users
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, track_active_users))

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
