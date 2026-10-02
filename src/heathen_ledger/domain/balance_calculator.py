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
        balances: dict[int, int] = {member.id: 0 for member in members}
        cls._apply_expenses(balances, expenses)
        cls._apply_payments(balances, payments)
        return balances

    @classmethod
    def _apply_expenses(cls, balances: dict[int, int], expenses: list[Any]) -> None:
        """Apply payers and splits from expenses to net balances."""
        for exp in expenses:
            for p in exp.payers:
                balances[p.user_id] = balances.get(p.user_id, 0) + p.amount

            for split in exp.splits:
                balances[split.user_id] = balances.get(split.user_id, 0) - split.amount

    @classmethod
    def _apply_payments(cls, balances: dict[int, int], payments: list[Any]) -> None:
        """Apply settlement payments to net balances."""
        for pay in payments:
            # Payer sent money -> their debt decreases / closer to settled (add amount)
            balances[pay.payer_id] = balances.get(pay.payer_id, 0) + pay.amount
            # Payee received money -> what they are owed decreases / closer to settled (subtract amount)
            balances[pay.payee_id] = balances.get(pay.payee_id, 0) - pay.amount
