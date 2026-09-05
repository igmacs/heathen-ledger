import os
import logging
from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import ApplicationBuilder, Application

from .handlers import register_handlers

# Re-exporting handlers for backward compatibility and test suitability

load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def post_init(application: Application) -> None:
    """Set the bot commands for autocompletion."""
    commands = [
        BotCommand("pay", "Log an expense split among members"),
        BotCommand("balances", "View current group balances"),
        BotCommand("settle", "Calculate payback transactions"),
        BotCommand("payback", "Record a direct payment"),
        BotCommand("history", "View last 10 transactions"),
        BotCommand("voice", "Transcribe and interpret a replied-to voice note"),
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

    # Register all command and callback handlers
    register_handlers(application)

    # Run the bot until the user presses Ctrl-C
    application.run_polling()
