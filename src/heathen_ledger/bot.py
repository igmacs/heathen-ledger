import logging
import os

from dotenv import load_dotenv
from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
)
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
    private_commands = [
        BotCommand("start", "Start the bot and get introduced"),
        BotCommand("help", "Display help message"),
    ]
    group_commands = [
        BotCommand(
            "pay",
            "Log an expense split among members",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "balances",
            "View current group balances",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "settle",
            "Calculate payback settlements",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "payback",
            "Record a direct payment",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "history",
            "View last 10 transactions",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "register",
            "Register a member",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "members",
            "List group members",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "voice",
            "Transcribe and interpret a replied-to voice note",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "ticket",
            "Scan a receipt photo to itemize expenses",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "close",
            "Close ledger and leave group (when settled)",
            api_kwargs={"is_ephemeral": True},
        ),
        BotCommand(
            "help",
            "Display help message",
            api_kwargs={"is_ephemeral": True},
        ),
    ]

    # Set commands for private chats / default scope
    await application.bot.set_my_commands(private_commands)
    try:
        await application.bot.set_my_commands(
            private_commands, scope=BotCommandScopeAllPrivateChats()
        )
    except Exception as e:
        logging.getLogger(__name__).warning(
            "Failed to set commands for private chats: %s", e
        )

    # In group chats, register group ledger commands as ephemeral
    try:
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
