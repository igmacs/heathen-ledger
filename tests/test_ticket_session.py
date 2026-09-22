import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.receipt import (
    Receipt,
    ReceiptItem,
    expand_receipt_items,
    extract_initials,
    PendingTicketSession,
    PendingTicketStore,
)


class TestTicketSession(unittest.TestCase):
    def test_expand_receipt_items(self):
        items = [
            ReceiptItem(name="Burger", price=12.00, quantity=1),
            ReceiptItem(name="Beer", price=10.50, quantity=3),
        ]
        expanded = expand_receipt_items(items)
        self.assertEqual(len(expanded), 4)
        self.assertEqual(expanded[0].name, "Burger")
        self.assertEqual(expanded[0].price, 12.00)
        self.assertEqual(expanded[0].quantity, 1)

        self.assertEqual(expanded[1].name, "Beer #1")
        self.assertEqual(expanded[1].price, 3.50)
        self.assertEqual(expanded[2].name, "Beer #2")
        self.assertEqual(expanded[2].price, 3.50)
        self.assertEqual(expanded[3].name, "Beer #3")
        self.assertEqual(expanded[3].price, 3.50)

    def test_expand_receipt_items_rounding_preservation(self):
        # 10.00 split across 3 items -> 3.33 + 3.33 + 3.34 = 10.00
        items = [ReceiptItem(name="Tapas", price=10.00, quantity=3)]
        expanded = expand_receipt_items(items)
        self.assertEqual(len(expanded), 3)
        self.assertEqual(expanded[0].price, 3.33)
        self.assertEqual(expanded[1].price, 3.33)
        self.assertEqual(expanded[2].price, 3.34)
        self.assertEqual(round(sum(it.price for it in expanded), 2), 10.00)

    def test_extract_initials(self):
        self.assertEqual(extract_initials("Ignacio", "García"), "IG")
        self.assertEqual(extract_initials("Alice"), "AL")
        self.assertEqual(extract_initials("John Doe"), "JD")
        self.assertEqual(extract_initials("B"), "B")
        self.assertEqual(extract_initials("", username="@cooluser"), "CO")
        self.assertEqual(extract_initials("", username="x"), "X")
        self.assertEqual(extract_initials(""), "??")

    def test_pending_ticket_session_creation(self):
        receipt = Receipt(
            merchant="Pizzeria",
            items=[
                ReceiptItem(name="Pizza", price=15.00, quantity=1),
                ReceiptItem(name="Beer", price=8.00, quantity=2),
            ],
            total=23.00,
        )
        session = PendingTicketSession.create(
            chat_id=123,
            creator_id=456,
            creator_name="Ignacio",
            receipt=receipt,
            token="test1234",
        )
        self.assertEqual(session.token, "test1234")
        self.assertEqual(len(session.items), 3)
        self.assertEqual(session.items[0].name, "Pizza")
        self.assertEqual(session.items[1].name, "Beer #1")
        self.assertEqual(session.items[2].name, "Beer #2")

    def test_toggle_participant(self):
        receipt = Receipt(items=[ReceiptItem(name="Pizza", price=12.00, quantity=1)])
        session = PendingTicketSession.create(
            chat_id=123, creator_id=456, creator_name="Ignacio", receipt=receipt
        )

        # Toggle on
        added = session.toggle_participant(
            item_index=0,
            user_id=101,
            display_name="Alice",
            username="alice",
        )
        self.assertTrue(added)
        self.assertEqual(len(session.items[0].participants), 1)
        self.assertEqual(session.items[0].initials_list, ["AL"])
        self.assertIn("👤 AL", session.items[0].initials_display)

        # Toggle another on (now multiple)
        added2 = session.toggle_participant(
            item_index=0,
            user_id=102,
            display_name="Bob",
            username="bob",
        )
        self.assertTrue(added2)
        self.assertEqual(len(session.items[0].participants), 2)
        self.assertIn("👥", session.items[0].initials_display)

        # Toggle Alice off
        removed = session.toggle_participant(
            item_index=0,
            user_id=101,
            display_name="Alice",
            username="alice",
        )
        self.assertFalse(removed)
        self.assertEqual(len(session.items[0].participants), 1)
        self.assertEqual(session.items[0].initials_list, ["BO"])

    def test_toggle_completed(self):
        receipt = Receipt(items=[ReceiptItem(name="Coffee", price=2.5)])
        session = PendingTicketSession.create(
            chat_id=123, creator_id=456, creator_name="Ignacio", receipt=receipt
        )
        self.assertFalse(session.items[0].is_completed)
        self.assertTrue(session.toggle_completed(0))
        self.assertTrue(session.items[0].is_completed)
        self.assertFalse(session.toggle_completed(0))
        self.assertFalse(session.items[0].is_completed)

    def test_assign_external_participant(self):
        receipt = Receipt(items=[ReceiptItem(name="Salad", price=8.0)])
        session = PendingTicketSession.create(
            chat_id=123, creator_id=456, creator_name="Ignacio", receipt=receipt
        )
        ok = session.assign_external_participant(0, "Carlos Guest")
        self.assertTrue(ok)
        self.assertIn("ext:carlos guest", session.items[0].participants)
        p = session.items[0].participants["ext:carlos guest"]
        self.assertEqual(p.display_name, "Carlos Guest")
        self.assertEqual(p.initials, "CG")
        self.assertTrue(p.is_external)

    def test_calculate_split_equal_and_tax(self):
        # Total receipt 24.00 (items sum to 20.00, tax 4.00)
        receipt = Receipt(
            items=[
                ReceiptItem(
                    name="Pizza", price=12.00, quantity=1
                ),  # shared Alice & Bob (6.00 each)
                ReceiptItem(name="Beer", price=4.00, quantity=1),  # Bob only (4.00)
                ReceiptItem(name="Wine", price=4.00, quantity=1),  # Alice only (4.00)
            ],
            total=24.00,
        )
        session = PendingTicketSession.create(
            chat_id=123, creator_id=456, creator_name="Ignacio", receipt=receipt
        )
        session.toggle_participant(0, user_id=1, display_name="Alice")
        session.toggle_participant(0, user_id=2, display_name="Bob")
        session.toggle_participant(1, user_id=2, display_name="Bob")
        session.toggle_participant(2, user_id=1, display_name="Alice")

        # Alice items: 6 + 4 = 10 (50%)
        # Bob items: 6 + 4 = 10 (50%)
        # Extra fees = 24.00 - 20.00 = 4.00
        # Alice extra = 2.00, Bob extra = 2.00
        # Total each = 12.00
        split = session.calculate_split()
        self.assertEqual(len(split), 2)
        self.assertEqual(split["tg:1"]["items_subtotal"], 10.00)
        self.assertEqual(split["tg:1"]["extra_fee_share"], 2.00)
        self.assertEqual(split["tg:1"]["total_share"], 12.00)

        self.assertEqual(split["tg:2"]["items_subtotal"], 10.00)
        self.assertEqual(split["tg:2"]["extra_fee_share"], 2.00)
        self.assertEqual(split["tg:2"]["total_share"], 12.00)

    def test_pending_ticket_store(self):
        store = PendingTicketStore(ttl_seconds=1)
        receipt = Receipt(items=[])
        session = PendingTicketSession.create(
            123, 456, "Ignacio", receipt, token="tok1"
        )
        store.store(session)

        self.assertEqual(store.get("tok1"), session)
        popped = store.pop("tok1")
        self.assertEqual(popped, session)
        self.assertIsNone(store.get("tok1"))


if __name__ == "__main__":
    unittest.main()
