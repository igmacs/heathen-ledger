from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session
from telegram import User as TgUser

from ..models import Group, User
from ..repositories import GroupRepository, UserRepository

logger = logging.getLogger(__name__)


@dataclass
class RegistrationResult:
    """Outcome of registering a single user."""

    success: bool
    user: User | None = None
    group: Group | None = None
    already_registered: bool = False
    error: str | None = None
    display_label: str = ""
    has_explicit_handle: bool = False


@dataclass
class RegistrationBatchResult:
    """Outcome of registering multiple users."""

    results: list[RegistrationResult]

    def __iter__(self):
        return iter(self.results)

    @property
    def registered(self) -> list[User]:
        return [
            r.user
            for r in self.results
            if r.success and not r.already_registered and r.user
        ]

    @property
    def already_registered(self) -> list[User]:
        return [
            r.user
            for r in self.results
            if r.success and r.already_registered and r.user
        ]


class MemberRegistrationService:
    """Service handling group member registrations."""

    @classmethod
    def register_user(
        cls,
        session: Session,
        group: Group | int,
        target: TgUser | int | str | Any,
        *,
        username: str | None = None,
        first_name: str | None = None,
        chat_title: str | None = None,
        commit: bool = True,
    ) -> RegistrationResult:
        """Register a single member (Telegram user, handle, or external person) into a group ledger."""
        group_repo = GroupRepository(session)
        user_repo = UserRepository(session)
        group_obj = cls._resolve_group(group_repo, group, chat_title)
        if not group_obj:
            return RegistrationResult(
                success=False,
                error=f"Group {group} does not exist.",
            )

        # Unwrap if passed a TEXT_MENTION entity
        if getattr(target, "type", None) == "text_mention" and hasattr(target, "user"):
            target = target.user

        # 1. Telegram user object
        if hasattr(target, "id") and hasattr(target, "is_bot"):
            return cls._register_telegram_user(
                session, user_repo, group_obj, target, commit
            )

        # 2. Integer Telegram ID
        if isinstance(target, int):
            return cls._register_by_telegram_id(
                session, user_repo, group_obj, target, username, first_name, commit
            )

        # 3. String (handle or name)
        if isinstance(target, str):
            return cls._register_string_user(
                session, user_repo, group_obj, target, username, first_name, commit
            )

        return RegistrationResult(
            success=False,
            error=f"Unsupported target type: {type(target).__name__}",
        )

    @classmethod
    def _resolve_group(
        cls,
        group_repo: GroupRepository,
        group: Group | int,
        chat_title: str | None = None,
    ) -> Group | None:
        if isinstance(group, int):
            return group_repo.get_by_telegram_id(group)
        return group

    @classmethod
    def _register_telegram_user(
        cls,
        session: Session,
        user_repo: UserRepository,
        group_obj: Group,
        target: Any,
        commit: bool,
    ) -> RegistrationResult:
        if target.is_bot:
            return RegistrationResult(
                success=False,
                error="Cannot register a bot.",
                display_label=target.first_name or "Bot",
            )
        return cls._register_by_telegram_id(
            session=session,
            user_repo=user_repo,
            group_obj=group_obj,
            tg_id=target.id,
            username=target.username,
            first_name=target.first_name or "",
            commit=commit,
        )

    @classmethod
    def _register_by_telegram_id(
        cls,
        session: Session,
        user_repo: UserRepository,
        group_obj: Group,
        tg_id: int,
        username: str | None,
        first_name: str | None,
        commit: bool,
    ) -> RegistrationResult:
        f_name = first_name or f"User{tg_id}"
        display_label = f"*{f_name}*"

        existing = next((m for m in group_obj.members if m.telegram_id == tg_id), None)
        if existing:
            return RegistrationResult(
                success=True,
                user=existing,
                group=group_obj,
                already_registered=True,
                display_label=display_label,
                has_explicit_handle=bool(username),
            )

        db_user = user_repo.get_or_create(
            telegram_id=tg_id,
            username=username,
            first_name=f_name,
        )
        user_repo.add_to_group(db_user, group_obj)
        if commit:
            session.commit()
        else:
            session.flush()
        return RegistrationResult(
            success=True,
            user=db_user,
            group=group_obj,
            already_registered=False,
            display_label=display_label,
            has_explicit_handle=bool(username),
        )

    @classmethod
    def _parse_string_target(
        cls, raw_str: str, username: str | None, first_name: str | None
    ) -> tuple[str, str, bool, str] | RegistrationResult:
        if raw_str.startswith("@"):
            clean_handle = raw_str.lstrip("@").strip().lower()
            if not clean_handle:
                return RegistrationResult(
                    success=False,
                    error="Invalid handle. Please specify a non-empty username.",
                    display_label=raw_str,
                )
            handle = clean_handle
            disp_name = first_name or handle.capitalize()
            return handle, disp_name, True, f"@{handle}"

        if username:
            handle = username.lstrip("@").strip().lower()
            disp_name = first_name or raw_str
            return handle, disp_name, True, f"@{handle}"

        parts = raw_str.split()
        if len(parts) == 1:
            disp_name = parts[0]
            handle = re.sub(r"[^\w]", "", parts[0]).lower()
        else:
            disp_name = raw_str
            handle = re.sub(r"[^\w]+", "_", raw_str).strip("_").lower()

        if not handle:
            return RegistrationResult(
                success=False,
                error="Invalid handle or name. Please use alphanumeric characters.",
                display_label=raw_str,
            )
        return handle, disp_name, False, f"*{disp_name}*"

    @classmethod
    def _register_string_user(
        cls,
        session: Session,
        user_repo: UserRepository,
        group_obj: Group,
        target: str,
        username: str | None,
        first_name: str | None,
        commit: bool,
    ) -> RegistrationResult:
        parsed = cls._parse_string_target(target.strip(), username, first_name)
        if isinstance(parsed, RegistrationResult):
            return parsed

        handle, disp_name, has_explicit_handle, display_label = parsed
        existing = next(
            (
                m
                for m in group_obj.members
                if m.username and m.username.lower() == handle
            ),
            None,
        )
        if existing:
            return RegistrationResult(
                success=True,
                user=existing,
                group=group_obj,
                already_registered=True,
                display_label=display_label,
                has_explicit_handle=has_explicit_handle,
            )

        glob_u = user_repo.get_in_group(group_obj.id, handle)
        if glob_u:
            if commit:
                session.commit()
            else:
                session.flush()
            return RegistrationResult(
                success=True,
                user=glob_u,
                group=group_obj,
                already_registered=False,
                display_label=display_label,
                has_explicit_handle=has_explicit_handle,
            )

        db_user = user_repo.create_external(
            group=group_obj,
            first_name=disp_name,
            username=handle,
        )
        if commit:
            session.commit()
        else:
            session.flush()
        return RegistrationResult(
            success=True,
            user=db_user,
            group=group_obj,
            already_registered=False,
            display_label=display_label,
            has_explicit_handle=has_explicit_handle,
        )

    @classmethod
    def register_users(
        cls,
        session: Session,
        group: Group | int,
        targets: Iterable[TgUser | int | str | Any],
        *,
        chat_title: str | None = None,
        commit: bool = True,
    ) -> RegistrationBatchResult:
        """Register multiple members in the group ledger."""
        results = []
        for target in targets:
            res = cls.register_user(
                session,
                group,
                target,
                chat_title=chat_title,
                commit=False,
            )
            results.append(res)

        if commit:
            session.commit()
        else:
            session.flush()

        return RegistrationBatchResult(results=results)

    @classmethod
    def get_group_members(cls, session: Session, chat_id: int) -> list[User] | None:
        """Retrieve the list of members for a group chat, or None if group doesn't exist."""
        group = GroupRepository(session).get_by_telegram_id(chat_id)
        if not group or not group.members:
            return None
        return group.members


# Aliases for convenience
MemberService = MemberRegistrationService
RegistrationService = MemberRegistrationService
