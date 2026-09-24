"""Domain service for calculating net balances across members."""

from typing import Any


class BalanceCalculator:
    """Calculates net financial balances among group members based on expenses and payments."""

    @classmethod
    def calculate_net_balances(
        cls,
        members: list[Any],
        expenses: list[Any],
        payments: list[Any],
    ) -> dict[int, int]:
        """Calculate the net balance for each member.

        Net Balance = (Paid in Expenses) - (Owed in Splits) + (Received in Payments) - (Sent in Payments)

        - Positive balance: The user is owed money (they paid more than they owed).
        - Negative balance: The user owes money (they owed more than they paid).
        - Zero balance: The user is fully settled up.

        :param members: List of User model instances belonging to the group.
        :param expenses: List of Expense model instances with payers and splits.
        :param payments: List of Payment model instances.
        :return: A dict mapping internal user IDs to their net balance in cents.
        """
        balances: dict[int, int] = {}

        # Initialize all members with a 0 balance
        for member in members:
            balances[member.id] = 0

        # 1. Process Expenses and Splits
        for exp in expenses:
            if getattr(exp, "payers", None):
                for p in exp.payers:
                    if p.user_id not in balances:
                        balances[p.user_id] = 0
                    balances[p.user_id] += p.amount

            if getattr(exp, "splits", None):
                for split in exp.splits:
                    if split.user_id not in balances:
                        balances[split.user_id] = 0
                    balances[split.user_id] -= split.amount

        # 2. Process Settlement Payments
        for pay in payments:
            if pay.payer_id not in balances:
                balances[pay.payer_id] = 0
            if pay.payee_id not in balances:
                balances[pay.payee_id] = 0

            # Payer sent money -> their debt decreases / closer to settled (add amount)
            balances[pay.payer_id] += pay.amount
            # Payee received money -> what they are owed decreases / closer to settled (subtract amount)
            balances[pay.payee_id] -= pay.amount

        return balances
