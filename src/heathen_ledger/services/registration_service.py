import asyncio
import logging
import re
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from telegram import User as TgUser

from ..models import Group
from ..repositories import UserRepository

logger = logging.getLogger(__name__)


class MemberRegistrationService:
    """Service handling multi-strategy group member registrations."""

    @classmethod
    async def resolve_admin_by_username(
        cls, context: Any, chat_id: int, username: str
    ) -> Optional[TgUser]:
        """Check if a username matches a chat administrator."""
        clean_username = username.lower().lstrip("@")
        if hasattr(context, "bot") and hasattr(context.bot, "get_chat_administrators"):
            try:
                res = context.bot.get_chat_administrators(chat_id)
                admins = await res if asyncio.iscoroutine(res) else res
                if isinstance(admins, (list, tuple)):
                    for adm in admins:
                        adm_u = getattr(adm, "user", None)
                        if adm_u and getattr(adm_u, "username", None):
                            if adm_u.username.lower() == clean_username:
                                return adm_u
            except Exception as e:
                logger.debug(f"Could not fetch chat administrators: {e}")
        return None

    @classmethod
    async def get_admins_by_username(
        cls, context: Any, chat_id: int
    ) -> Dict[str, TgUser]:
        """Fetch all chat administrators indexed by lowercase username."""
        admins_by_username = {}
        if hasattr(context, "bot") and hasattr(context.bot, "get_chat_administrators"):
            try:
                res = context.bot.get_chat_administrators(chat_id)
                admins = await res if asyncio.iscoroutine(res) else res
                if isinstance(admins, (list, tuple)):
                    for adm in admins:
                        adm_u = getattr(adm, "user", None)
                        if adm_u and getattr(adm_u, "username", None):
                            admins_by_username[adm_u.username.lower()] = adm_u
            except Exception as e:
                logger.debug(f"Could not fetch chat admins: {e}")
        return admins_by_username

    @classmethod
    def register_reply_user(
        cls, session: Session, group: Group, target_user: TgUser
    ) -> Tuple[bool, str]:
        """Register the author of a replied-to message."""
        if target_user.is_bot:
            return False, "⚠️ Cannot register a bot."

        if any(m.telegram_id == target_user.id for m in group.members):
            handle_str = f" (`@{target_user.username}`)" if target_user.username else ""
            return (
                True,
                f"ℹ️ Member *{target_user.first_name}*{handle_str} is already registered in this group.",
            )

        user_repo = UserRepository(session)
        db_user = user_repo.get_or_create(
            telegram_id=target_user.id,
            username=target_user.username,
            first_name=target_user.first_name,
        )
        user_repo.add_to_group(db_user, group)
        session.commit()

        handle_str = f" (`@{target_user.username}`)" if target_user.username else ""
        return (
            True,
            f"✅ Registered member *{target_user.first_name}*{handle_str} to this group ledger.",
        )

    @classmethod
    def register_text_mentions(
        cls, session: Session, group: Group, text_mentions: List[Any]
    ) -> Tuple[List[str], List[str]]:
        """Register users extracted from TEXT_MENTION message entities."""
        registered_names = []
        already_registered_names = []
        user_repo = UserRepository(session)

        for tm in text_mentions:
            u = tm.user
            if u.is_bot:
                continue
            if any(m.telegram_id == u.id for m in group.members):
                already_registered_names.append(u.first_name)
                continue
            db_u = user_repo.get_or_create(
                telegram_id=u.id, username=u.username, first_name=u.first_name
            )
            user_repo.add_to_group(db_u, group)
            registered_names.append(u.first_name)

        session.commit()
        return registered_names, already_registered_names

    @classmethod
    def register_mentions(
        cls,
        session: Session,
        group: Group,
        mentions: List[str],
        admins_by_username: Dict[str, TgUser],
    ) -> Tuple[List[str], List[str]]:
        """Register multiple @mentions provided as arguments."""
        registered = []
        already_registered = []
        user_repo = UserRepository(session)

        for h in mentions:
            if any(m.username and m.username.lower() == h for m in group.members):
                already_registered.append(f"@{h}")
                continue
            if h in admins_by_username:
                adm_u = admins_by_username[h]
                db_u = user_repo.get_or_create(
                    adm_u.id, adm_u.username, adm_u.first_name
                )
                user_repo.add_to_group(db_u, group)
                registered.append(f"@{h}")
                continue
            # Search globally
            glob_u = user_repo.get_in_group(group.id, h)
            if glob_u:
                registered.append(f"@{h}")
                continue
            # Register as external/pending user
            user_repo.create_external(group, h.capitalize(), username=h)
            registered.append(f"@{h}")

        session.commit()
        return registered, already_registered

    @classmethod
    def register_handle(
        cls,
        session: Session,
        group: Group,
        handle: str,
        first_name: str,
        admin_u: Optional[TgUser],
    ) -> str:
        """Register a single @handle (as admin, global user, or external user)."""
        user_repo = UserRepository(session)

        for m in group.members:
            if m.username and m.username.lower() == handle:
                return f"ℹ️ Member *{m.first_name}* (`@{handle}`) is already registered in this group."

        if admin_u:
            db_u = user_repo.get_or_create(
                admin_u.id, admin_u.username, admin_u.first_name
            )
            user_repo.add_to_group(db_u, group)
            session.commit()
            return f"✅ Registered member *{db_u.first_name}* (`@{handle}`) to this group ledger."

        # Check if registered Telegram user globally
        glob_u = user_repo.get_in_group(group.id, handle)
        if glob_u:
            session.commit()
            return f"✅ Registered member *{glob_u.first_name}* (`@{handle}`) to this group ledger."

        # Register external / pending user
        user_repo.create_external(
            group=group,
            first_name=first_name,
            username=handle,
        )
        session.commit()
        return (
            f"✅ Registered *{first_name}* (`@{handle}`) in this group ledger.\n\n"
            f"They can now be included in expenses and settlements. "
            f"When @{handle} interacts with the bot or taps Register, their account will link automatically."
        )

    @classmethod
    def register_name(
        cls, session: Session, group: Group, name_text: str
    ) -> Tuple[bool, str]:
        """Register an external member by name without @handle."""
        parts = name_text.split()
        if len(parts) == 1:
            first_name = parts[0]
            handle = re.sub(r"[^\w]", "", parts[0]).lower()
        else:
            first_name = name_text
            handle = re.sub(r"[^\w]+", "_", name_text).strip("_").lower()

        if not handle:
            return (
                False,
                "⚠️ Invalid handle or name. Please use alphanumeric characters.",
            )

        for m in group.members:
            if m.username and m.username.lower() == handle:
                return (
                    True,
                    f"ℹ️ Member *{m.first_name}* (`@{handle}`) is already registered in this group.",
                )

        user_repo = UserRepository(session)
        user_repo.create_external(
            group=group,
            first_name=first_name,
            username=handle,
        )
        session.commit()
        return (
            True,
            f"✅ Registered external member *{first_name}* (`@{handle}`) to this group.\n\n"
            f"You can now include them in expenses (e.g. `/pay 50 split @{handle}`) or settlements.",
        )
