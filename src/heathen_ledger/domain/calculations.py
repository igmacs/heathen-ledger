"""Financial calculations: equal splits, remainder distribution, and debt simplification."""

from typing import Any


def split_amount_equally(amount: int, num_people: int) -> list[int]:
    """
    Splits an integer amount of cents as equally as possible among a number of people.
    Distributes any rounding remainders (modulus) to the first few people to prevent losing pennies.

    For example, splitting 1000 cents (10.00) among 3 people returns [334, 333, 333].

    :param amount: Total amount in cents.
    :param num_people: Number of people to split between.
    :return: A list of length `num_people` with individual split shares.
    """
    if num_people <= 0:
        return []

    base_share = amount // num_people
    remainder = amount % num_people

    shares = [base_share] * num_people
    for i in range(remainder):
        shares[i] += 1

    return shares


def simplify_debts(balances: dict[int, int]) -> list[dict[str, Any]]:
    """
    Computes the minimum number of transactions needed to settle all debts using a greedy algorithm.

    :param balances: A dict mapping user IDs to their net balances in cents.
    :return: A list of dicts representing transactions:
             {
                 'from_user_id': int,
                 'to_user_id': int,
                 'amount': int  # in cents
             }
    """
    debtors = []  # list of [user_id, amount_cents]
    creditors = []  # list of [user_id, amount_cents]

    for user_id, balance in balances.items():
        if balance < 0:
            debtors.append([user_id, -balance])
        elif balance > 0:
            creditors.append([user_id, balance])

    # Sort descending by amount so we process largest balances first
    debtors.sort(key=lambda x: x[1], reverse=True)
    creditors.sort(key=lambda x: x[1], reverse=True)

    transactions = []

    while debtors and creditors:
        debtor = debtors[0]
        creditor = creditors[0]

        from_id, owe_amt = debtor
        to_id, owed_amt = creditor

        settle_amt = min(owe_amt, owed_amt)
        if settle_amt == 0:
            break

        transactions.append(
            {"from_user_id": from_id, "to_user_id": to_id, "amount": settle_amt}
        )

        debtor[1] -= settle_amt
        creditor[1] -= settle_amt

        if debtor[1] == 0:
            debtors.pop(0)
        else:
            debtors.sort(key=lambda x: x[1], reverse=True)

        if creditor[1] == 0:
            creditors.pop(0)
        else:
            creditors.sort(key=lambda x: x[1], reverse=True)

    return transactions
