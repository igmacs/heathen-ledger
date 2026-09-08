import datetime
import os
import sys
import unittest

# Add project src to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from heathen_ledger.parser import (
    parse_pay_message,
    split_amount_equally,
    generate_balances_summary,
    simplify_debts,
    generate_settlements_summary,
    parse_payback_message,
    generate_history_summary,
)


class TestParser(unittest.TestCase):
    def test_parse_pay_message_with_payer_and_desc(self):
        res = parse_pay_message("/pay @Alice 50 for Dinner")
        self.assertEqual(res.get("payer_username"), "alice")
        self.assertEqual(res.get("amount"), 5000)
        self.assertEqual(res.get("participants"), [])
        self.assertEqual(res.get("description"), "Dinner")

    def test_parse_pay_message_with_payer_and_participants(self):
        res = parse_pay_message("/pay @Alice 50 for @Bob @Charlie")
        self.assertEqual(res.get("payer_username"), "alice")
        self.assertEqual(res.get("amount"), 5000)
        self.assertEqual(res.get("participants"), ["bob", "charlie"])
        self.assertIsNone(res.get("description"))

    def test_parse_pay_message_no_payer(self):
        res = parse_pay_message("/pay 12.50 for lunch @Bob")
        self.assertIsNone(res.get("payer_username"))
        self.assertEqual(res.get("amount"), 1250)
        self.assertEqual(res.get("participants"), ["bob"])
        self.assertEqual(res.get("description"), "lunch")

    def test_parse_pay_message_only_amount(self):
        res = parse_pay_message("/pay 100")
        self.assertIsNone(res.get("payer_username"))
        self.assertEqual(res.get("amount"), 10000)
        self.assertEqual(res.get("participants"), [])
        self.assertIsNone(res.get("description"))

    def test_parse_pay_message_invalid_amount(self):
        res = parse_pay_message("/pay @Alice for Dinner")
        self.assertIn("error", res)

    def test_parse_pay_message_multi_payer_equal(self):
        res = parse_pay_message("/pay 90 for Dinner by me @Bob")
        self.assertNotIn("error", res)
        self.assertEqual(res["amount"], 9000)
        self.assertEqual(res["description"], "Dinner")
        self.assertEqual(res["payers"], {"me": 4500, "bob": 4500})
        self.assertIsNone(res["payer_username"])

    def test_parse_pay_message_multi_payer_custom(self):
        res = parse_pay_message("/pay 40 for Pizza by me:25 @Charlie:15")
        self.assertNotIn("error", res)
        self.assertEqual(res["amount"], 4000)
        self.assertEqual(res["description"], "Pizza")
        self.assertEqual(res["payers"], {"me": 2500, "charlie": 1500})

    def test_parse_pay_message_inferred_amount_from_payers(self):
        res = parse_pay_message("/pay for Dinner by @Alice:30 @Bob:20")
        self.assertNotIn("error", res)
        self.assertEqual(res["amount"], 5000)
        self.assertEqual(res["payers"], {"alice": 3000, "bob": 2000})
        self.assertEqual(res["description"], "Dinner")

    def test_parse_pay_message_custom_splits(self):
        res = parse_pay_message("/pay 30 for drinks split @Bob:10 @Charlie:20")
        self.assertNotIn("error", res)
        self.assertEqual(res["amount"], 3000)
        self.assertEqual(res["description"], "drinks")
        self.assertEqual(res["split_spec"]["mode"], "custom")
        self.assertEqual(res["split_spec"]["shares"], {"bob": 1000, "charlie": 2000})
        self.assertEqual(res["participants"], ["bob", "charlie"])

    def test_parse_pay_message_split_except(self):
        res = parse_pay_message("/pay 45 for groceries split except @Dave")
        self.assertNotIn("error", res)
        self.assertEqual(res["amount"], 4500)
        self.assertEqual(res["description"], "groceries")
        self.assertEqual(res["split_spec"]["mode"], "except")
        self.assertEqual(res["split_spec"]["excluded"], ["dave"])

    def test_parse_pay_message_dates(self):
        # ISO date
        res_iso = parse_pay_message("/pay 50 for Dinner on 2026-09-07")
        self.assertNotIn("error", res_iso)
        self.assertEqual(res_iso["expense_date"], datetime.date(2026, 9, 7))

        # today & yesterday
        res_today = parse_pay_message("/pay 50 for Lunch on today")
        self.assertEqual(res_today["expense_date"], datetime.date.today())

        res_yesterday = parse_pay_message("/pay 50 for Lunch on yesterday")
        self.assertEqual(
            res_yesterday["expense_date"],
            datetime.date.today() - datetime.timedelta(days=1),
        )

        # Invalid date
        res_invalid = parse_pay_message("/pay 50 for Lunch on 2026-99-99")
        self.assertIn("error", res_invalid)

    def test_parse_pay_message_quoted_description(self):
        res = parse_pay_message('/pay 120 for "Weekend Airbnb and snacks" by @Alice')
        self.assertNotIn("error", res)
        self.assertEqual(res["amount"], 12000)
        self.assertEqual(res["description"], "Weekend Airbnb and snacks")
        self.assertEqual(res["payers"], {"alice": 12000})

    def test_parse_pay_message_validation_mismatched_payers(self):
        res = parse_pay_message("/pay 50 for Dinner by @Alice:30 @Bob:10")
        self.assertIn("error", res)
        self.assertIn("does not match total expense amount", res["error"])

    def test_parse_pay_message_validation_mismatched_splits(self):
        res = parse_pay_message("/pay 50 for Dinner split @Bob:20 @Charlie:20")
        self.assertIn("error", res)
        self.assertIn("does not match total expense amount", res["error"])

    def test_split_amount_equally_exact(self):
        shares = split_amount_equally(3000, 3)
        self.assertEqual(shares, [1000, 1000, 1000])

    def test_split_amount_equally_with_remainder(self):
        # 10.00 / 3 -> 3.34, 3.33, 3.33
        shares = split_amount_equally(1000, 3)
        self.assertEqual(shares, [334, 333, 333])

        # 0.05 / 3 -> 0.02, 0.02, 0.01
        shares = split_amount_equally(5, 3)
        self.assertEqual(shares, [2, 2, 1])

    def test_generate_balances_summary(self):
        class MockUser:
            def __init__(self, first_name):
                self.first_name = first_name

        users_by_id = {
            1: MockUser("Alice"),
            2: MockUser("Bob"),
            3: MockUser("Charlie"),
        }

        balances = {
            1: 2000,  # Alice is owed $20.00
            2: -1000,  # Bob owes $10.00
            3: 0,  # Charlie is settled up
        }

        summary = generate_balances_summary(balances, users_by_id)

        self.assertIn("📊 **Current Net Balances:**", summary)
        self.assertIn("• **Alice** is owed **$20.00**", summary)
        self.assertIn("• **Bob** owes **$10.00**", summary)
        self.assertIn("• **Charlie** is settled up", summary)

        # Verify sorting order (descending balance)
        lines = summary.split("\n")
        self.assertTrue("Alice" in lines[1])
        self.assertTrue("Charlie" in lines[2])
        self.assertTrue("Bob" in lines[3])

    def test_simplify_debts_simple(self):
        balances = {1: 2000, 2: -1000, 3: -1000}
        txs = simplify_debts(balances)
        self.assertEqual(len(txs), 2)

        tx1 = next(t for t in txs if t["from_user_id"] == 2)
        self.assertEqual(tx1["to_user_id"], 1)
        self.assertEqual(tx1["amount"], 1000)

        tx2 = next(t for t in txs if t["from_user_id"] == 3)
        self.assertEqual(tx2["to_user_id"], 1)
        self.assertEqual(tx2["amount"], 1000)

    def test_simplify_debts_complex(self):
        balances = {1: 3000, 2: -1000, 3: -2000}
        txs = simplify_debts(balances)
        self.assertEqual(len(txs), 2)

        tx_charlie = next(t for t in txs if t["from_user_id"] == 3)
        self.assertEqual(tx_charlie["to_user_id"], 1)
        self.assertEqual(tx_charlie["amount"], 2000)

        tx_bob = next(t for t in txs if t["from_user_id"] == 2)
        self.assertEqual(tx_bob["to_user_id"], 1)
        self.assertEqual(tx_bob["amount"], 1000)

    def test_generate_settlements_summary(self):
        class MockUser:
            def __init__(self, first_name):
                self.first_name = first_name

        users_by_id = {1: MockUser("Alice"), 2: MockUser("Bob")}

        txs = [{"from_user_id": 2, "to_user_id": 1, "amount": 1500}]
        summary = generate_settlements_summary(txs, users_by_id)

        self.assertIn("🤝 **Suggested Payments to Settle Up:**", summary)
        self.assertIn("• **Bob** should pay **Alice** **$15.00**", summary)

    def test_parse_payback_message_single_mention(self):
        res = parse_payback_message("/payback @Alice 10")
        self.assertIsNone(res.get("payer_username"))
        self.assertEqual(res.get("payee_username"), "alice")
        self.assertEqual(res.get("amount"), 1000)

    def test_parse_payback_message_dual_mention(self):
        res = parse_payback_message("/payback @Bob @Alice 12.50")
        self.assertEqual(res.get("payer_username"), "bob")
        self.assertEqual(res.get("payee_username"), "alice")
        self.assertEqual(res.get("amount"), 1250)

    def test_parse_payback_message_invalid(self):
        res = parse_payback_message("/payback @Alice")
        self.assertIn("error", res)

    def test_generate_history_summary(self):
        class MockUser:
            def __init__(self, first_name):
                self.first_name = first_name

        class MockExpense:
            def __init__(self, payer, amount, description):
                self.payer = payer
                self.payer_id = 1
                self.amount = amount
                self.description = description

        class MockPayment:
            def __init__(self, payer, payee, amount):
                self.payer = payer
                self.payer_id = 1
                self.payee = payee
                self.payee_id = 2
                self.amount = amount

        alice = MockUser("Alice")
        bob = MockUser("Bob")
        exp = MockExpense(alice, 5000, "Dinner")
        pay = MockPayment(bob, alice, 2000)

        txs = [
            {"type": "expense", "obj": exp, "created_at": None},
            {"type": "payment", "obj": pay, "created_at": None},
        ]

        summary = generate_history_summary(txs)
        self.assertIn("📜 **Recent Group History:**", summary)
        self.assertIn(
            "1. 💸 **Expense:** **Alice** paid **$50.00** for 'Dinner'", summary
        )
        self.assertIn("2. 🤝 **Payment:** **Bob** paid **Alice** **$20.00**", summary)


if __name__ == "__main__":
    unittest.main()
