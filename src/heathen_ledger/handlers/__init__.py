from telegram.constants import MessageEntityType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from .registration import (
    auto_register,
    register_command,
    register_callback_handler,
)
from .members import members_command
from .start import start
from .help import help_command
from .common import dismiss_callback_handler, persist_callback_handler
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
    voice_callback_handler,
)
from .receipt import (
    ticket_command_handler,
    ticket_photo_handler,
    ticket_mention_handler,
    ticket_callback_handler,
    ticket_external_reply_handler,
)


async def reply_mention_dispatcher(update, context):
    """Dispatch reply mentions to voice or receipt handlers depending on media type."""
    if not update.message or not update.message.reply_to_message:
        return
    reply_to = update.message.reply_to_message
    if reply_to.voice or reply_to.audio:
        await voice_mention_handler(update, context)
    elif reply_to.photo or (
        reply_to.document
        and getattr(reply_to.document, "mime_type", "").startswith("image/")
    ):
        await ticket_mention_handler(update, context)


def register_handlers(application: Application) -> None:
    """Register all command and callback handlers to the application."""
    # Add auto-registration handler in a separate group (-1) so it runs before command handlers (group 0)
    application.add_handler(MessageHandler(filters.ALL, auto_register), group=-1)

    # Voice / Audio and Receipt reply mention handler
    application.add_handler(
        MessageHandler(
            filters.REPLY
            & (
                filters.Entity(MessageEntityType.MENTION)
                | filters.Entity(MessageEntityType.TEXT_MENTION)
            ),
            reply_mention_dispatcher,
        )
    )

    # Receipt photo handler (direct photos in private chats, or captioned photos with command/mention)
    application.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.IMAGE,
            ticket_photo_handler,
        )
    )

    # Ticket external participant name reply handler
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            ticket_external_reply_handler,
        )
    )

    # Command Handlers (ephemeral in group chats)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pay", pay_command))
    application.add_handler(CommandHandler("balances", balances_command))
    application.add_handler(CommandHandler("settle", settle_command))
    application.add_handler(CommandHandler("payback", payback_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("voice", voice_command_handler))
    application.add_handler(
        CommandHandler(["ticket", "receipt"], ticket_command_handler)
    )
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("members", members_command))
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
        CallbackQueryHandler(register_callback_handler, pattern="^register:join$")
    )
    application.add_handler(
        CallbackQueryHandler(voice_callback_handler, pattern="^voice:")
    )
    application.add_handler(
        CallbackQueryHandler(ticket_callback_handler, pattern="^tkt:")
    )
    application.add_handler(
        CallbackQueryHandler(persist_callback_handler, pattern="^persist:")
    )
    application.add_handler(
        CallbackQueryHandler(dismiss_callback_handler, pattern="^dismiss(:.*)?$")
    )
