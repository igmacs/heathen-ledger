import logging
import re
from typing import Any

from sqlalchemy.orm import Session
from telegram import User as TgUser

from ..models import Group, User
from ..repositories import GroupRepository, UserRepository

logger = logging.getLogger(__name__)


class MemberRegistrationService:
    """Service handling multi-strategy group member registrations."""

    @classmethod
    def register_reply_user(
        cls, session: Session, group: Group, target_user: TgUser
    ) -> tuple[bool, str]:
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
        cls, session: Session, group: Group, text_mentions: list[Any]
    ) -> tuple[list[str], list[str]]:
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
        mentions: list[str],
    ) -> tuple[list[str], list[str]]:
        """Register multiple @mentions provided as arguments."""
        registered = []
        already_registered = []
        user_repo = UserRepository(session)

        for h in mentions:
            if any(m.username and m.username.lower() == h for m in group.members):
                already_registered.append(f"@{h}")
                continue
            # Search globally for registered Telegram user
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
    ) -> str:
        """Register a single @handle (as global user or external user)."""
        user_repo = UserRepository(session)

        for m in group.members:
            if m.username and m.username.lower() == handle:
                return f"ℹ️ Member *{m.first_name}* (`@{handle}`) is already registered in this group."

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
    ) -> tuple[bool, str]:
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

    @classmethod
    def auto_register_user_and_group(
        cls,
        session: Session,
        user_id: int,
        chat_id: int,
        username: str | None = None,
        first_name: str = "",
        chat_title: str | None = None,
    ) -> tuple[User, Group]:
        """Automatically register user and group chat if not already existing, and link them."""
        user_repo = UserRepository(session)
        group_repo = GroupRepository(session)

        db_user = user_repo.get_or_create(
            telegram_id=user_id, username=username, first_name=first_name
        )
        title = chat_title or f"Chat ({chat_id})"
        db_group = group_repo.get_or_create(telegram_chat_id=chat_id, title=title)
        user_repo.add_to_group(user=db_user, group=db_group)
        session.commit()
        return db_user, db_group

    @classmethod
    def register_self(
        cls,
        session: Session,
        chat_id: int,
        user: TgUser,
        chat_title: str | None = None,
    ) -> tuple[bool, User, Group]:
        """Handle inline button click for self-registration.

        Returns:
            (already_registered: bool, db_user: User, db_group: Group)
        """
        group_repo = GroupRepository(session)
        user_repo = UserRepository(session)

        group = group_repo.get_by_telegram_id(chat_id)
        if not group:
            title = chat_title or f"Chat ({chat_id})"
            group = group_repo.get_or_create(telegram_chat_id=chat_id, title=title)

        already_registered = any(m.telegram_id == user.id for m in group.members)
        if already_registered:
            db_user = user_repo.get_by_telegram_id(user.id)
            return True, db_user, group

        db_user = user_repo.get_or_create(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name or "",
        )
        user_repo.add_to_group(db_user, group)
        session.commit()
        return False, db_user, group

    @classmethod
    def get_group_members(cls, session: Session, chat_id: int) -> list[User] | None:
        """Retrieve the list of members for a group chat, or None if group doesn't exist."""
        group = GroupRepository(session).get_by_telegram_id(chat_id)
        if not group or not group.members:
            return None
        return group.members

    @classmethod
    def ensure_member_in_group(
        cls,
        session: Session,
        chat_id: int,
        user_id: int,
        username: str | None = None,
        first_name: str = "",
        chat_title: str | None = None,
    ) -> tuple[User, Group]:
        """Ensure both group and user exist and the user is linked to the group."""
        group_repo = GroupRepository(session)
        user_repo = UserRepository(session)

        group = group_repo.get_by_telegram_id(chat_id)
        if not group:
            group = group_repo.get_or_create(telegram_chat_id=chat_id, title=chat_title)

        user = user_repo.get_by_telegram_id(user_id)
        if not user:
            user = user_repo.get_or_create(
                telegram_id=user_id,
                username=username,
                first_name=first_name or f"User{user_id}",
            )
        user_repo.add_to_group(user, group)
        session.flush()
        return user, group


# Aliases for convenience
MemberService = MemberRegistrationService
RegistrationService = MemberRegistrationService
