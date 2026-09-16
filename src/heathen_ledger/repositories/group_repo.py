import logging
from typing import Optional
from sqlalchemy.orm import Session
from ..models import Group

logger = logging.getLogger(__name__)


class GroupRepository:
    """Repository for Group persistence and retrieval."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_telegram_id(self, telegram_chat_id: int) -> Optional[Group]:
        """Retrieve a group by its Telegram chat ID."""
        return (
            self.session.query(Group)
            .filter(Group.telegram_chat_id == telegram_chat_id)
            .first()
        )

    def get_by_id(self, group_id: int) -> Optional[Group]:
        """Retrieve a group by its primary key ID."""
        return self.session.query(Group).filter(Group.id == group_id).first()

    def get_or_create(
        self, telegram_chat_id: int, title: Optional[str] = None
    ) -> Group:
        """Get an existing group chat or register a new one if it does not exist."""
        group = self.get_by_telegram_id(telegram_chat_id)
        if not group:
            group = Group(telegram_chat_id=telegram_chat_id, title=title)
            self.session.add(group)
            self.session.flush()
            logger.info(
                f"Registered new group chat: {title} (Chat ID: {telegram_chat_id})"
            )
        else:
            if title is not None and group.title != title:
                group.title = title
        return group
