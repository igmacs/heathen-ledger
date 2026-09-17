import logging
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from ..database import with_db_session
from ..services import MemberRegistrationService
from .common import send_response

logger = logging.getLogger(__name__)


@with_db_session
async def members_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session
):
    """List all registered members in the current group ledger."""
    if not update.effective_chat or not update.message:
        return

    members = MemberRegistrationService.get_group_members(
        session, update.effective_chat.id
    )
    if not members:
        await send_response(
            update,
            context,
            "ℹ️ No members are currently registered in this group ledger.",
        )
        return

    lines = ["👥 **Group Members:**\n"]
    for idx, m in enumerate(members, 1):
        handle = f" (@{m.username})" if m.username else ""
        ext_tag = " _[external]_" if m.is_external else ""
        lines.append(f"{idx}. **{m.first_name}**{handle}{ext_tag}")

    await send_response(update, context, "\n".join(lines), parse_mode="Markdown")
