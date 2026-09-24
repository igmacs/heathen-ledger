import logging
from sqlalchemy.orm import Session
from ..models import User, Group

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for User persistence, retrieval, and group membership management."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Retrieve a user by their unique Telegram user ID."""
        return self.session.query(User).filter(User.telegram_id == telegram_id).first()

    def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str = "",
    ) -> User:
        """Get an existing user or create a new user registry if they do not exist."""
        user = self.get_by_telegram_id(telegram_id)
        if not user:
            if username:
                clean_username = username.lower().lstrip("@")
                external_user = (
                    self.session.query(User)
                    .filter(
                        User.username == clean_username,
                        User.is_external.is_(True),
                        User.telegram_id.is_(None),
                    )
                    .first()
                )
                if external_user:
                    external_user.telegram_id = telegram_id
                    external_user.is_external = False
                    if first_name:
                        external_user.first_name = first_name
                    logger.info(
                        f"Linked external user @{clean_username} to Telegram ID {telegram_id}"
                    )
                    return external_user

            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_external=False,
            )
            self.session.add(user)
            self.session.flush()
            logger.info(
                f"Registered new user: {first_name} (Telegram ID: {telegram_id})"
            )
        else:
            if username is not None and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
        return user

    def create_external(
        self,
        group: Group,
        first_name: str,
        username: str | None = None,
    ) -> User:
        """Register an external user (without a Telegram account) and add them to the group."""
        clean_username = username.lower().lstrip("@") if username else None
        user = User(
            telegram_id=None,
            username=clean_username,
            first_name=first_name,
            is_external=True,
        )
        self.session.add(user)
        self.session.flush()
        self.add_to_group(user, group)
        logger.info(
            f"Registered external user: {first_name} (@{clean_username}) in group {group.title}"
        )
        return user

    def get_in_group(
        self,
        group_id: int,
        username: str,
    ) -> User | None:
        """Find a user in a specific group by username or first name.

        Falls back to globally registered Telegram users if not yet in group.
        """
        clean_name = username.strip().lower().lstrip("@")
        group = self.session.query(Group).filter(Group.id == group_id).first()
        if group:
            for m in group.members:
                if m.username and m.username.lower() == clean_name:
                    return m
            for m in group.members:
                if m.first_name and m.first_name.lower() == clean_name:
                    return m

        fallback_user = (
            self.session.query(User)
            .filter(User.username == clean_name, User.is_external.is_(False))
            .first()
        )
        if fallback_user and group:
            self.add_to_group(fallback_user, group)
        return fallback_user

    def add_to_group(self, user: User, group: Group) -> bool:
        """Add a user to a group chat's member list if not already present."""
        if user not in group.members:
            group.members.append(user)
            logger.info(f"Added user {user.first_name} to group {group.title}")
            return True
        return False
