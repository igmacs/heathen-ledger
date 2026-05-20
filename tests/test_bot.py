import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock
from contextlib import contextmanager

# Add project root to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import crud
from bot import settle_callback_handler, undo_callback_handler

# We mock database session injection because get_session inside @with_db_session
# needs to point to our in-memory test database session.
# We will mock/patch the get_session context manager inside bot.py.


class TestBotSettleCallback(unittest.TestCase):
    def setUp(self):
        # 1. Setup in-memory SQLite database
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)

        # 2. Patch database.get_session to return our test session
        self.db_session = self.Session()
        self.get_session_patcher = unittest.mock.patch(
            "database.get_session",
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

        # Let's create an expense to settle: Alice paid $30.00 for all 3 (split is 10.00 each)
        splits = {self.alice.id: 1000, self.bob.id: 1000, self.charlie.id: 1000}
        crud.create_expense(
            self.db_session,
            group_id=self.group.id,
            payer_id=self.alice.id,
            amount=3000,
            description="Test Expense",
            splits=splits,
        )
        self.db_session.commit()

    @contextmanager
    def get_session_context(self, session):
        yield session

    def tearDown(self):
        self.get_session_patcher.stop()
        self.db_session.close()
        Base.metadata.drop_all(bind=self.engine)

    def create_mock_update(self, telegram_user_id, callback_data):
        update = MagicMock()
        query = AsyncMock()
        query.data = callback_data

        # Mock query.from_user
        from_user = MagicMock()
        from_user.id = telegram_user_id
        query.from_user = from_user

        # Mock query.message
        message = MagicMock()
        chat = MagicMock()
        chat.id = 12345
        message.chat = chat
        query.message = message

        update.callback_query = query
        return update

    async def run_settle_callback(self, update):
        context = MagicMock()
        await settle_callback_handler(update, context)

    def test_callback_security_unauthorized_user(self):
        # Charlie is not part of Alice <-> Bob transaction (Bob owes Alice 10.00)
        # Charlie attempts to confirm Bob paid Alice
        callback_data = f"settle:{self.bob.id}:{self.alice.id}:1000"
        update = self.create_mock_update(
            telegram_user_id=33, callback_data=callback_data
        )  # Charlie's telegram ID is 33

        # Run the callback handler
        import asyncio

        asyncio.run(self.run_settle_callback(update))

        # Charlie should receive an alert warning
        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Only Bob or Alice can confirm", kwargs.get("text"))

        # No payments should be created in the database
        payments = crud.get_group_payments(self.db_session, self.group.id)
        self.assertEqual(len(payments), 0)

    def test_callback_authorized_payer(self):
        # Bob confirms he paid Alice
        callback_data = f"settle:{self.bob.id}:{self.alice.id}:1000"
        update = self.create_mock_update(
            telegram_user_id=22, callback_data=callback_data
        )  # Bob's telegram ID is 22

        import asyncio

        asyncio.run(self.run_settle_callback(update))

        # Check payment recorded
        payments = crud.get_group_payments(self.db_session, self.group.id)
        self.assertEqual(len(payments), 1)
        self.assertEqual(payments[0].payer_id, self.bob.id)
        self.assertEqual(payments[0].payee_id, self.alice.id)
        self.assertEqual(payments[0].amount, 1000)

        # Check message update
        update.callback_query.answer.assert_called_once()
        self.assertIn(
            "Recorded: Bob paid Alice",
            update.callback_query.answer.call_args.kwargs.get("text"),
        )
        update.callback_query.edit_message_text.assert_called_once()

    def test_callback_authorized_payee(self):
        # Alice confirms Bob paid her
        callback_data = f"settle:{self.bob.id}:{self.alice.id}:1000"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )  # Alice's telegram ID is 11

        import asyncio

        asyncio.run(self.run_settle_callback(update))

        # Check payment recorded
        payments = crud.get_group_payments(self.db_session, self.group.id)
        self.assertEqual(len(payments), 1)

        # Check update message editing
        update.callback_query.edit_message_text.assert_called_once()

    async def run_undo_callback(self, update):
        context = MagicMock()
        await undo_callback_handler(update, context)

    def test_undo_security_unauthorized_user(self):
        # Alice created an expense. Charlie tries to undo it.
        # Setup an expense: Alice paid $30.00
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"undo:expense:{expense.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=33, callback_data=callback_data
        )  # Charlie is ID 33

        import asyncio

        asyncio.run(self.run_undo_callback(update))

        # Check Charlie is rejected with show_alert
        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Only Alice can undo", kwargs.get("text"))

        # Expense should NOT be deleted
        self.assertEqual(
            len(crud.get_group_expenses(self.db_session, self.group.id)), 1
        )

    def test_undo_authorized_creator_expense(self):
        # Alice (creator) undos the expense she recorded
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"undo:expense:{expense.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )  # Alice is ID 11

        import asyncio

        asyncio.run(self.run_undo_callback(update))

        # Check expense deleted
        self.assertEqual(
            len(crud.get_group_expenses(self.db_session, self.group.id)), 0
        )
        update.callback_query.answer.assert_called_once_with(text="Transaction undone.")
        update.callback_query.edit_message_text.assert_called_once()
        kwargs = update.callback_query.edit_message_text.call_args.kwargs
        self.assertIn("has been undone by Alice", kwargs.get("text"))

    def test_undo_authorized_creator_payment(self):
        # Bob records a payment of $5.00 to Alice
        payment = crud.create_payment(
            self.db_session, self.group.id, self.bob.id, self.alice.id, 500
        )
        self.db_session.commit()

        # Bob undos the payment
        callback_data = f"undo:payment:{payment.id}:{self.bob.id}"
        update = self.create_mock_update(
            telegram_user_id=22, callback_data=callback_data
        )  # Bob is ID 22

        import asyncio

        asyncio.run(self.run_undo_callback(update))

        # Check payment deleted
        self.assertEqual(
            len(crud.get_group_payments(self.db_session, self.group.id)), 0
        )
        update.callback_query.answer.assert_called_once_with(text="Transaction undone.")
        update.callback_query.edit_message_text.assert_called_once()
        kwargs = update.callback_query.edit_message_text.call_args.kwargs
        self.assertIn("has been undone by Bob", kwargs.get("text"))


if __name__ == "__main__":
    unittest.main()
