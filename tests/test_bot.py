import sys
import os
import unittest
from unittest.mock import AsyncMock, MagicMock
from contextlib import contextmanager

# Add project src to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from heathen_ledger.database import Base
from heathen_ledger import crud
from heathen_ledger.handlers.settle import settle_callback_handler
from heathen_ledger.handlers.expense import (
    undo_callback_handler,
    pay_toggle_callback_handler,
)
from heathen_ledger.handlers.history import history_delete_callback_handler
from heathen_ledger.handlers.common import dismiss_callback_handler

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
        message.delete = AsyncMock()
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

    async def run_history_delete_callback(self, update):
        context = MagicMock()
        await history_delete_callback_handler(update, context)

    def test_history_delete_security_unauthorized_user(self):
        # Alice created an expense (paid by Alice). Charlie tries to delete it.
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"hist_del:expense:{expense.id}"
        update = self.create_mock_update(
            telegram_user_id=33, callback_data=callback_data
        )  # Charlie is ID 33

        import asyncio

        asyncio.run(self.run_history_delete_callback(update))

        # Check Charlie is rejected with show_alert
        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Only Alice can delete", kwargs.get("text"))

        # Expense should NOT be deleted
        self.assertEqual(
            len(crud.get_group_expenses(self.db_session, self.group.id)), 1
        )

    def test_history_delete_authorized_expense(self):
        # Alice (payer) deletes the expense she paid
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"hist_del:expense:{expense.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )  # Alice is ID 11

        import asyncio

        asyncio.run(self.run_history_delete_callback(update))

        # Check expense deleted
        self.assertEqual(
            len(crud.get_group_expenses(self.db_session, self.group.id)), 0
        )
        update.callback_query.answer.assert_called_once_with(text="Expense deleted.")
        update.callback_query.edit_message_text.assert_called_once()

    def test_history_delete_authorized_payment(self):
        # Bob records a payment of $5.00 to Alice
        payment = crud.create_payment(
            self.db_session, self.group.id, self.bob.id, self.alice.id, 500
        )
        self.db_session.commit()

        # Bob (payer) deletes the payment
        callback_data = f"hist_del:payment:{payment.id}"
        update = self.create_mock_update(
            telegram_user_id=22, callback_data=callback_data
        )  # Bob is ID 22

        import asyncio

        asyncio.run(self.run_history_delete_callback(update))

        # Check payment deleted
        self.assertEqual(
            len(crud.get_group_payments(self.db_session, self.group.id)), 0
        )
        update.callback_query.answer.assert_called_once_with(text="Payment deleted.")
        update.callback_query.edit_message_text.assert_called_once()

    async def run_dismiss_callback(self, update):
        context = MagicMock()
        await dismiss_callback_handler(update, context)

    def test_dismiss_callback(self):
        update = self.create_mock_update(telegram_user_id=11, callback_data="dismiss")
        reply_to_mock = AsyncMock()
        update.callback_query.message.reply_to_message = reply_to_mock

        import asyncio

        asyncio.run(self.run_dismiss_callback(update))

        reply_to_mock.delete.assert_called_once()
        update.callback_query.message.delete.assert_called_once()
        update.callback_query.answer.assert_called_once()

    def test_dismiss_callback_bad_request(self):
        from telegram.error import BadRequest

        update = self.create_mock_update(telegram_user_id=11, callback_data="dismiss")
        reply_to_mock = AsyncMock()
        reply_to_mock.delete.side_effect = BadRequest("Cannot delete user message")
        update.callback_query.message.reply_to_message = reply_to_mock

        update.callback_query.message.delete.side_effect = BadRequest(
            "Message to delete not found"
        )

        import asyncio

        asyncio.run(self.run_dismiss_callback(update))

        reply_to_mock.delete.assert_called_once()
        update.callback_query.message.delete.assert_called_once()
        update.callback_query.answer.assert_called_once()

    async def run_pay_toggle_callback(self, update):
        context = MagicMock()
        await pay_toggle_callback_handler(update, context)

    def test_pay_toggle_security_unauthorized_user(self):
        # Alice created the expense. Charlie tries to toggle Bob out of the split.
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        callback_data = f"pay_toggle:{expense.id}:{self.bob.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=33, callback_data=callback_data
        )  # Charlie is ID 33

        import asyncio

        asyncio.run(self.run_pay_toggle_callback(update))

        # Check Charlie is rejected with show_alert
        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Only Alice can edit", kwargs.get("text"))

    def test_pay_toggle_remove_participant(self):
        # Alice toggles Bob out of the split (initially split equally: Alice, Bob, Charlie)
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        self.assertEqual(len(expense.splits), 3)

        callback_data = f"pay_toggle:{expense.id}:{self.bob.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )  # Alice is ID 11

        import asyncio

        asyncio.run(self.run_pay_toggle_callback(update))

        # Check splits in database
        self.db_session.expire_all()
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        self.assertEqual(len(expense.splits), 2)

        # Verify splits recalculated (amount is 30.00 split between 2: Alice, Charlie get 15.00 each)
        splits_dict = {s.user_id: s.amount for s in expense.splits}
        self.assertNotIn(self.bob.id, splits_dict)
        self.assertEqual(splits_dict[self.alice.id], 1500)
        self.assertEqual(splits_dict[self.charlie.id], 1500)

        # Verify message text updated
        update.callback_query.edit_message_text.assert_called_once()
        kwargs = update.callback_query.edit_message_text.call_args.kwargs
        self.assertIn("Alice: $15.00", kwargs.get("text"))
        self.assertIn("Charlie: $15.00", kwargs.get("text"))
        self.assertNotIn("Bob:", kwargs.get("text"))

    def test_pay_toggle_add_participant(self):
        # First, remove Bob so splits are Alice, Charlie
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        for split in list(expense.splits):
            if split.user_id == self.bob.id:
                self.db_session.delete(split)
        self.db_session.commit()

        # Alice toggles Bob back in
        callback_data = f"pay_toggle:{expense.id}:{self.bob.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )  # Alice is ID 11

        import asyncio

        asyncio.run(self.run_pay_toggle_callback(update))

        # Check splits in database (Bob is back)
        self.db_session.expire_all()
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        self.assertEqual(len(expense.splits), 3)

        # Verify splits recalculated to 10.00 each
        splits_dict = {s.user_id: s.amount for s in expense.splits}
        self.assertEqual(splits_dict[self.bob.id], 1000)
        self.assertEqual(splits_dict[self.alice.id], 1000)
        self.assertEqual(splits_dict[self.charlie.id], 1000)

    def test_pay_toggle_prevent_removing_last_participant(self):
        # Remove Bob and Charlie from the split first
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        for split in list(expense.splits):
            if split.user_id != self.alice.id:
                self.db_session.delete(split)
        expense.splits[0].amount = 3000
        self.db_session.commit()

        # Alice tries to toggle Alice off (leaving 0 participants)
        callback_data = f"pay_toggle:{expense.id}:{self.alice.id}:{self.alice.id}"
        update = self.create_mock_update(
            telegram_user_id=11, callback_data=callback_data
        )  # Alice is ID 11

        import asyncio

        asyncio.run(self.run_pay_toggle_callback(update))

        # Check alert shown
        update.callback_query.answer.assert_called_once()
        kwargs = update.callback_query.answer.call_args.kwargs
        self.assertTrue(kwargs.get("show_alert"))
        self.assertIn("Cannot remove the last participant", kwargs.get("text"))

        # Check splits in database (Alice is still there)
        self.db_session.expire_all()
        expense = crud.get_group_expenses(self.db_session, self.group.id)[0]
        self.assertEqual(len(expense.splits), 1)
        self.assertEqual(expense.splits[0].user_id, self.alice.id)


if __name__ == "__main__":
    unittest.main()
