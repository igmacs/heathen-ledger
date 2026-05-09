from typing import Dict, List, Tuple


def calculate_settlements(balances: Dict[str, float]) -> List[Tuple[str, str, float]]:
    """
    Calculates the minimum number of transactions needed to settle all debts.

    Args:
        balances: A dictionary mapping usernames to their net balance.
                  Positive means they are owed money. Negative means they owe money.

    Returns:
        A list of tuples representing transactions: (debtor, creditor, amount)
        Meaning "debtor owes creditor amount".
    """
    debtors = []  # List of [username, amount_owed] (positive amounts for easier math)
    creditors = []  # List of [username, amount_to_receive] (positive amounts)

    for user, balance in balances.items():
        if balance < -0.01:  # Use a small epsilon for floating point issues
            debtors.append([user, abs(balance)])
        elif balance > 0.01:
            creditors.append([user, balance])

    # Sort by amount descending to greedily settle largest debts first
    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)

    transactions = []

    i = 0  # Debtors index
    j = 0  # Creditors index

    while i < len(debtors) and j < len(creditors):
        debtor_name, debtor_amount = debtors[i]
        creditor_name, creditor_amount = creditors[j]

        # The transfer is the minimum of what the debtor owes and what the creditor is owed
        transfer_amount = min(debtor_amount, creditor_amount)
        transfer_amount = round(transfer_amount, 2)

        transactions.append((debtor_name, creditor_name, transfer_amount))

        # Update remaining amounts
        debtors[i][1] -= transfer_amount
        creditors[j][1] -= transfer_amount

        # Move to the next person if their debt/credit is settled
        if debtors[i][1] < 0.01:
            i += 1
        if creditors[j][1] < 0.01:
            j += 1

    return transactions
