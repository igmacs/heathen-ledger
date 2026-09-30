"""Handlers for group lifecycle events: joining, leaving, and group updates."""

import asyncio
import logging

from sqlalchemy.orm import Session
from telegram import Update
from telegram.constants import ChatMemberStatus, ChatType
from telegram.ext import ContextTypes

from ..database import with_db_session
from ..repositories import GroupRepository

logger = logging.getLogger(__name__)

GREETING_MESSAGE = (
    "👋 **Hello! I am Heathen Ledger.**\n\n"
    '_*"This group deserves a better class of ledger, and I’m gonna give it to ‘em."*_\n\n'
    "I help you track and settle shared expenses in group chats. Type /help to see all available commands."
)


def _is_active_status(status: str | None) -> bool:
    return status in (
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    )


async def _send_welcome_greeting(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> None:
    bot = getattr(context, "bot", None)
    if not bot or not hasattr(bot, "send_message"):
        return
    try:
        res = bot.send_message(
            chat_id=chat_id,
            text=GREETING_MESSAGE,
            parse_mode="Markdown",
        )
        if asyncio.iscoroutine(res):
            await res
    except Exception as e:
        logger.debug("Could not send greeting to group %s: %s", chat_id, e)


@with_db_session
async def chat_member_update_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
) -> None:
    """Handle updates to the bot's membership status in chats (my_chat_member).

    When the bot enters a Telegram group or supergroup, this immediately initializes
    the group ledger in the database and posts a welcome greeting.
    """
    chat_member_updated = update.my_chat_member
    if not chat_member_updated:
        return

    chat = chat_member_updated.chat
    if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    old_status = getattr(chat_member_updated.old_chat_member, "status", None)
    new_status = getattr(chat_member_updated.new_chat_member, "status", None)

    # Bot joined or was added to group / promoted to active status from inactive
    if _is_active_status(new_status) and not _is_active_status(old_status):
        group_repo = GroupRepository(session)
        title = chat.title or f"Chat ({chat.id})"
        group_repo.get_or_create(telegram_chat_id=chat.id, title=title)
        session.commit()
        logger.info(
            "Bot joined group chat: %s (Chat ID: %s). Created group ledger.",
            title,
            chat.id,
        )
        await _send_welcome_greeting(context, chat.id)

    # NOTE: Group title updates (filters.StatusUpdate.NEW_CHAT_TITLE) and group ID
    # migrations to supergroup (filters.StatusUpdate.MIGRATE) can be handled here if needed in the future.
