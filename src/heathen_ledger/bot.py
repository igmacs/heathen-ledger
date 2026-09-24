import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import Application, ApplicationBuilder

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
        BotCommand("settle", "Calculate payback settlements"),
        BotCommand("payback", "Record a direct payment"),
        BotCommand("history", "View last 10 transactions"),
        BotCommand("register", "Register a member"),
        BotCommand("members", "List group members"),
        BotCommand("voice", "Transcribe and interpret a replied-to voice note"),
        BotCommand("ticket", "Scan a receipt photo to itemize expenses"),
        BotCommand("close", "Close ledger and leave group (when settled)"),
        BotCommand("help", "Display help message"),
    ]
    await application.bot.set_my_commands(commands)
    try:
        from telegram import BotCommandScopeAllGroupChats

        # In group chats, ALL commands are registered as ephemeral commands
        # so the user's invocation is hidden from the group.
        group_commands = [
            BotCommand(
                cmd.command,
                cmd.description,
                api_kwargs={"is_ephemeral": True},
            )
            for cmd in commands
        ]
        await application.bot.set_my_commands(
            group_commands, scope=BotCommandScopeAllGroupChats()
        )
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Failed to set commands for all group chats: %s", e
        )


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
