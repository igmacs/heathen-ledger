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
        BotCommand("pay", "Log an expense split among members (private response)"),
        BotCommand("pay_persistent", "Log an expense and post announcement to group"),
        BotCommand("balances", "View current group balances (private response)"),
        BotCommand("balances_persistent", "Post group balances sheet to group"),
        BotCommand("settle", "Calculate payback settlements (private response)"),
        BotCommand(
            "settle_persistent", "Post payback settlements with buttons to group"
        ),
        BotCommand("payback", "Record a direct payment (private response)"),
        BotCommand("payback_persistent", "Record a direct payment and post to group"),
        BotCommand("history", "View last 10 transactions (private response)"),
        BotCommand("history_persistent", "Post last 10 transactions to group"),
        BotCommand("register", "Register a member (private response)"),
        BotCommand("register_persistent", "Post member registration button to group"),
        BotCommand("members", "List group members (private response)"),
        BotCommand("members_persistent", "Post group members list to group"),
        BotCommand("voice", "Transcribe and interpret a replied-to voice note"),
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
