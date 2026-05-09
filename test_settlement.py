import unittest
from settlement import calculate_settlements

class TestSettlement(unittest.TestCase):
    def test_simple_settlement(self):
        # Alice owes 20, Bob is owed 20
        balances = {'@Alice': -20.0, '@Bob': 20.0}
        transactions = calculate_settlements(balances)
        self.assertEqual(len(transactions), 1)
        self.assertIn(('@Alice', '@Bob', 20.0), transactions)

    def test_multiple_settlements(self):
        # Alice is owed 50
        # Bob owes 20
        # Charlie owes 30
        balances = {'@Alice': 50.0, '@Bob': -20.0, '@Charlie': -30.0}
        transactions = calculate_settlements(balances)
        self.assertEqual(len(transactions), 2)
        # Charlie owes Alice 30, Bob owes Alice 20 (or vice versa, order doesn't matter much here, but our greedy approach sorts by amount)
        self.assertIn(('@Charlie', '@Alice', 30.0), transactions)
        self.assertIn(('@Bob', '@Alice', 20.0), transactions)
        
    def test_circular_debts(self):
        # A owes B 10, B owes C 10, C owes A 10. Net balances are 0.
        balances = {'@A': 0.0, '@B': 0.0, '@C': 0.0}
        transactions = calculate_settlements(balances)
        self.assertEqual(len(transactions), 0)

    def test_complex_settlement(self):
        # A is owed 100
        # B owes 50
        # C owes 40
        # D is owed 20
        # E owes 30
        # Net: 100 + 20 - 50 - 40 - 30 = 0
        balances = {'@A': 100.0, '@B': -50.0, '@C': -40.0, '@D': 20.0, '@E': -30.0}
        transactions = calculate_settlements(balances)
        
        # Checking net results of transactions
        new_balances = {k: 0.0 for k in balances.keys()}
        for debtor, creditor, amount in transactions:
            new_balances[debtor] -= amount
            new_balances[creditor] += amount
            
        for user, balance in balances.items():
            self.assertAlmostEqual(balance, new_balances[user])

if __name__ == '__main__':
    unittest.main()
