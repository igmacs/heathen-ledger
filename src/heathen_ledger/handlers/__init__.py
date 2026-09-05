from telegram.constants import MessageEntityType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from .base import auto_register, start, help_command
from .common import dismiss_callback_handler
from .expense import (
    pay_command,
    payback_command,
    undo_callback_handler,
    pay_toggle_callback_handler,
)
from .settle import balances_command, settle_command, settle_callback_handler
from .history import history_command, history_delete_callback_handler
from .voice import (
    voice_command_handler,
    voice_mention_handler,
)


def register_handlers(application: Application) -> None:
    """Register all command and callback handlers to the application."""
    # Add auto-registration handler in a separate group (-1) so it runs before command handlers (group 0)
    application.add_handler(MessageHandler(filters.ALL, auto_register), group=-1)

    # Voice / Audio reply mention handler
    application.add_handler(
        MessageHandler(
            filters.REPLY
            & (
                filters.Entity(MessageEntityType.MENTION)
                | filters.Entity(MessageEntityType.TEXT_MENTION)
            ),
            voice_mention_handler,
        )
    )

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pay", pay_command))
    application.add_handler(CommandHandler("balances", balances_command))
    application.add_handler(CommandHandler("settle", settle_command))
    application.add_handler(CommandHandler("payback", payback_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("voice", voice_command_handler))
    application.add_handler(CommandHandler("help", help_command))

    # Callback Query Handlers
    application.add_handler(
        CallbackQueryHandler(pay_toggle_callback_handler, pattern="^pay_toggle:")
    )
    application.add_handler(
        CallbackQueryHandler(settle_callback_handler, pattern="^settle:")
    )
    application.add_handler(
        CallbackQueryHandler(undo_callback_handler, pattern="^undo:")
    )
    application.add_handler(
        CallbackQueryHandler(history_delete_callback_handler, pattern="^hist_del:")
    )
    application.add_handler(
        CallbackQueryHandler(dismiss_callback_handler, pattern="^dismiss$")
    )
