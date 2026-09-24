import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.receipt import (
    Receipt,
    ReceiptItem,
    PendingTicketSession,
)
from heathen_ledger.receipt.formatter import (
    format_price,
    format_ticket_rich_html,
    format_ticket_split_summary,
)
from heathen_ledger.keyboards import TicketKeyboardBuilder


class TestTicketUI(unittest.TestCase):
    def test_format_price(self):
        self.assertEqual(format_price(10.5, "€"), "10.50 €")
        self.assertEqual(format_price(10.5, "$"), "$10.50")
        self.assertEqual(format_price(10.5, None), "10.50")

    def test_format_ticket_rich_html_basic(self):
        receipt = Receipt(
            merchant="Bistro & Co",
            items=[
                ReceiptItem(name="Pizza", price=12.00, quantity=1),
                ReceiptItem(name="Beer", price=6.00, quantity=2),
            ],
            subtotal=18.00,
            tax=1.80,
            total=19.80,
            currency="€",
        )
        session = PendingTicketSession.create(
            chat_id=123,
            creator_id=456,
            creator_name="Ignacio",
            receipt=receipt,
            token="t123",
        )
        # Add participant to Pizza
        session.toggle_participant(0, user_id=1, display_name="Alice")
        # Mark Beer #1 as completed
        session.toggle_completed(1)

        html = format_ticket_rich_html(session)
        self.assertIn("Bistro &amp; Co", html)
        self.assertIn("tkt:m:t123:0", html)
        self.assertIn("👤 +Me", html)
        self.assertIn("(👤 AL)", html)
        # Pizza line not completed
        self.assertIn("1. Pizza — 12.00 €", html)
        # Beer #1 line completed (strikethrough and undo button)
        self.assertIn("<s>✅ 2. Beer #1 — 3.00 €</s>", html)
        self.assertIn("tkt:d:t123:1", html)
        self.assertIn("↩️", html)
        # Progress status
        self.assertIn("1/3 items claimed", html)

    def test_format_ticket_split_summary(self):
        receipt = Receipt(merchant="Cafe", total=20.00, currency="€")
        session = PendingTicketSession.create(123, 456, "Ignacio", receipt)
        shares = {
            "tg:1": {
                "display_name": "Alice",
                "username": "alice",
                "user_id": 1,
                "initials": "AL",
                "is_external": False,
                "items_subtotal": 10.00,
                "extra_fee_share": 1.00,
                "total_share": 11.00,
            },
            "ext:bob": {
                "display_name": "Bob",
                "username": None,
                "user_id": None,
                "initials": "BO",
                "is_external": True,
                "items_subtotal": 8.00,
                "extra_fee_share": 1.00,
                "total_share": 9.00,
            },
        }
        summary = format_ticket_split_summary(session, shares)
        self.assertIn("Bill Split Summary", summary)
        self.assertIn("Cafe", summary)
        self.assertIn("*Alice* (@alice): *11.00 €*", summary)
        self.assertIn("*Bob* _(external)_: *9.00 €*", summary)

    def test_ticket_keyboard_builder(self):
        kb_main = TicketKeyboardBuilder.build_main_ticket_keyboard("t1")
        self.assertEqual(len(kb_main.inline_keyboard), 2)
        self.assertIn("tkt:asgn:t1", kb_main.inline_keyboard[0][0].callback_data)
        self.assertIn("tkt:fin:t1", kb_main.inline_keyboard[0][1].callback_data)
        self.assertIn("tkt:cancel:t1", kb_main.inline_keyboard[1][0].callback_data)

        receipt = Receipt(items=[ReceiptItem("A", 1), ReceiptItem("B", 2)])
        session = PendingTicketSession.create(1, 2, "Test", receipt, token="t1")
        kb_items = TicketKeyboardBuilder.build_item_selector_keyboard(session)
        self.assertGreater(len(kb_items.inline_keyboard), 1)

        mock_user = MagicMock()
        mock_user.id = 12
        mock_user.first_name = "Charlie"
        kb_members = TicketKeyboardBuilder.build_member_selector_keyboard(
            "t1", 0, [mock_user], "Pizza"
        )
        self.assertIn(
            "tkt:asgn_usr:t1:0:12", kb_members.inline_keyboard[0][0].callback_data
        )

        kb_split = TicketKeyboardBuilder.build_split_confirmation_keyboard("t1")
        self.assertIn("tkt:record:t1", kb_split.inline_keyboard[0][0].callback_data)

    def test_person_selector_and_checklist_keyboards(self):
        receipt = Receipt(
            items=[ReceiptItem("Pizza", 12.0), ReceiptItem("Beer", 4.0)],
            currency="€",
        )
        session = PendingTicketSession.create(1, 2, "Test", receipt, token="tokA")
        session.register_external_participant("David")
        session.toggle_participant_by_key(0, "ext:david")

        mock_member = MagicMock()
        mock_member.id = 99
        mock_member.telegram_id = 999
        mock_member.first_name = "Alice"

        # 1. Person selector keyboard
        kb_persons = TicketKeyboardBuilder.build_person_selector_keyboard(
            session, [mock_member]
        )
        cb_datas = [
            btn.callback_data for row in kb_persons.inline_keyboard for btn in row
        ]
        self.assertIn("tkt:psel:tokA:tg:999", cb_datas)
        self.assertIn("tkt:psel:tokA:ext:david", cb_datas)
        self.assertIn("tkt:asgn_new:tokA", cb_datas)
        self.assertIn("tkt:back:tokA", cb_datas)

        # 2. Checklist keyboard for David
        kb_check = TicketKeyboardBuilder.build_person_checklist_keyboard(
            session, "ext:david"
        )
        self.assertEqual(len(kb_check.inline_keyboard), 3)  # 2 items + 1 action row
        # Item 0 was claimed -> ☑️
        self.assertIn("☑️", kb_check.inline_keyboard[0][0].text)
        self.assertIn("Pizza", kb_check.inline_keyboard[0][0].text)
        self.assertEqual(
            kb_check.inline_keyboard[0][0].callback_data,
            "tkt:ptog:tokA:ext:david:0",
        )
        # Item 1 was not claimed -> ◻️
        self.assertIn("◻️", kb_check.inline_keyboard[1][0].text)
        self.assertIn("Beer", kb_check.inline_keyboard[1][0].text)
        self.assertEqual(
            kb_check.inline_keyboard[1][0].callback_data,
            "tkt:ptog:tokA:ext:david:1",
        )
        # Action row
        self.assertEqual(kb_check.inline_keyboard[2][0].callback_data, "tkt:back:tokA")
        self.assertEqual(kb_check.inline_keyboard[2][1].callback_data, "tkt:asgn:tokA")


if __name__ == "__main__":
    unittest.main()
