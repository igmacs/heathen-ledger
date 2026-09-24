"""Shared test fixtures, in-memory database setup, and mock Telegram update helpers."""

import unittest
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock

from heathen_ledger import crud
from heathen_ledger.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class BaseDatabaseTestCase(unittest.TestCase):
    """Base test fixture providing an in-memory SQLite database, patched session, and seeded group/users."""

    def setUp(self):
        # 1. Setup in-memory SQLite database
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)

        # 2. Patch database.get_session to return our test session
        self.db_session = self.Session()
        self.session = self.db_session  # Alias for convenience
        self.get_session_patcher = unittest.mock.patch(
            "heathen_ledger.database.get_session",
            side_effect=lambda: self.get_session_context(self.db_session),
        )
        self.get_session_patcher.start()

        # 3. Create mock users and group
        self.group = crud.get_or_create_group(self.db_session, 12345, "Test Group")
        self.alice = crud.get_or_create_user(self.db_session, 11, "alice", "Alice")
        self.bob = crud.get_or_create_user(self.db_session, 22, "bob", "Bob")
        self.charlie = crud.get_or_create_user(
            self.db_session, 33, "charlie", "Charlie"
        )

        crud.add_user_to_group(self.db_session, self.alice, self.group)
        crud.add_user_to_group(self.db_session, self.bob, self.group)
        crud.add_user_to_group(self.db_session, self.charlie, self.group)
        self.db_session.commit()

    @contextmanager
    def get_session_context(self, session):
        yield session

    def tearDown(self):
        self.get_session_patcher.stop()
        self.db_session.close()
        Base.metadata.drop_all(bind=self.engine)

    def create_mock_update(
        self,
        telegram_user_id,
        callback_data,
        chat_id=12345,
        username="user",
        first_name=None,
    ):
        """Create a mock Telegram Update with CallbackQuery."""
        update = MagicMock()
        query = AsyncMock()
        query.data = callback_data

        from_user = MagicMock()
        from_user.id = telegram_user_id
        from_user.username = username
        from_user.first_name = first_name or f"User{telegram_user_id}"
        from_user.is_bot = False
        query.from_user = from_user

        message = MagicMock()
        message.delete = AsyncMock()
        message.reply_text = AsyncMock()
        from telegram.constants import ChatType

        chat = MagicMock()
        chat.id = chat_id
        chat.type = ChatType.GROUP
        message.chat = chat
        message.reply_to_message = None
        query.message = message

        update.callback_query = query
        update.effective_user = from_user
        update.effective_chat = chat
        update.effective_message = message
        return update

    def create_mock_message_update(
        self,
        text,
        sender_telegram_id=11,
        sender_username="alice",
        sender_first_name="Alice",
        chat_id=12345,
        chat_title="Test Group",
    ):
        """Create a mock Telegram Update with text Message."""
        update = MagicMock()
        message = MagicMock()
        message.text = text
        message.reply_to_message = None
        message.reply_text = AsyncMock()

        user = MagicMock()
        user.id = sender_telegram_id
        user.username = sender_username
        user.first_name = sender_first_name
        from telegram.constants import ChatType

        chat = MagicMock()
        chat.id = chat_id
        chat.title = chat_title
        chat.type = ChatType.GROUP

        update.message = message
        update.effective_message = message
        update.effective_user = user
        update.effective_chat = chat
        return update
