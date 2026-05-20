import re
from typing import Optional, List, Dict, Any


def parse_pay_message(text: str) -> Dict[str, Any]:
    """
    Parses a /pay command message to extract expense details.

    Expected formats:
    - /pay [<payer>] <amount> [for <description>]
    - /pay [<payer>] <amount> [for <participants>]

    Examples:
    - /pay @Alice 50 for Dinner -> Payer: Alice, Amount: 5000, Description: Dinner
    - /pay @Alice 50 for @Bob @Charlie -> Payer: Alice, Amount: 5000, Participants: [Bob, Charlie]
    - /pay 12.50 -> Payer: None (default sender), Amount: 1250, Participants: []

    :param text: The raw text of the message.
    :return: A dictionary containing:
             - 'payer_username': Username of the payer (lowercase, no @), or None
             - 'amount': Amount in cents (int), or None if parsing fails
             - 'participants': List of participant usernames (lowercase, no @)
             - 'description': Description string, or None
             - 'error': Error message string if parsing fails
    """
    # 1. Strip the /pay command prefix
    cleaned_text = re.sub(r"^/pay(?:\s+|$)", "", text, flags=re.IGNORECASE).strip()

    # Find all @mentions with their character start/end positions
    mentions: List[Dict[str, Any]] = []
    for match in re.finditer(r"@(\w+)", cleaned_text):
        mentions.append(
            {
                "username": match.group(1).lower(),
                "start": match.start(),
                "end": match.end(),
            }
        )

    # Find the first numeric amount (integer or decimal up to 2 decimal places)
    amount_match = re.search(r"\b(\d+(?:\.\d{1,2})?)\b", cleaned_text)
    if not amount_match:
        return {"error": "No valid amount found in the message."}

    amount_str = amount_match.group(1)
    amount_start = amount_match.start()
    amount_end = amount_match.end()

    # Convert amount to integer cents
    if "." in amount_str:
        parts = amount_str.split(".")
        dollars = int(parts[0])
        cents_part = parts[1]
        cents = int(cents_part) * 10 if len(cents_part) == 1 else int(cents_part)
        amount_cents = dollars * 100 + cents
    else:
        amount_cents = int(amount_str) * 100

    # Resolve payer: the first mention that appears before the amount
    payer_username: Optional[str] = None
    for m in mentions:
        if m["end"] <= amount_start:
            payer_username = m["username"]
            break

    # Resolve participants: all mentions that appear after the amount
    participants: List[str] = []
    for m in mentions:
        if m["start"] >= amount_end:
            participants.append(m["username"])

    # Extract description:
    # If the 'for' keyword exists, grab the text following it, then filter out mentions.
    description: Optional[str] = None
    for_match = re.search(r"\bfor\b", cleaned_text, re.IGNORECASE)
    if for_match:
        after_for = cleaned_text[for_match.end() :].strip()
        # Clean out mentions and extra spaces
        desc_cleaned = re.sub(r"@\w+", "", after_for).strip()
        desc_cleaned = re.sub(r"\s+", " ", desc_cleaned)
        if desc_cleaned:
            description = desc_cleaned
    else:
        # Default description: whatever text remains after the amount (excluding mentions)
        after_amount = cleaned_text[amount_end:].strip()
        desc_cleaned = re.sub(r"@\w+", "", after_amount).strip()
        desc_cleaned = re.sub(r"\s+", " ", desc_cleaned)
        if desc_cleaned:
            description = desc_cleaned

    return {
        "payer_username": payer_username,
        "amount": amount_cents,
        "participants": participants,
        "description": description,
    }


def split_amount_equally(amount: int, num_people: int) -> List[int]:
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


def generate_balances_summary(
    balances: Dict[int, int], users_by_id: Dict[int, Any]
) -> str:
    """
    Formats the net balances of group members into a human-readable Markdown string.
    """
    if not balances:
        return "ℹ️ No member balances to display."

    lines = []
    # Sort by balance descending (people who are owed the most first)
    sorted_balances = sorted(balances.items(), key=lambda item: item[1], reverse=True)

    for user_id, balance in sorted_balances:
        user = users_by_id.get(user_id)
        if not user:
            continue
        name = getattr(user, "first_name", f"User {user_id}")
        amount = abs(balance) / 100

        if balance > 0:
            lines.append(f"• **{name}** is owed **${amount:.2f}**")
        elif balance < 0:
            lines.append(f"• **{name}** owes **${amount:.2f}**")
        else:
            lines.append(f"• **{name}** is settled up")

    return "📊 **Current Net Balances:**\n" + "\n".join(lines)


def simplify_debts(balances: Dict[int, int]) -> List[Dict[str, Any]]:
    """
    Computes the minimum number of transactions needed to settle all debts.

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


def generate_settlements_summary(
    transactions: List[Dict[str, Any]], users_by_id: Dict[int, Any]
) -> str:
    """
    Formats the list of suggested payments into a human-readable Markdown string.
    """
    if not transactions:
        return "✅ **Everyone is fully settled up! No transactions needed.**"

    lines = []
    for tx in transactions:
        from_user = users_by_id.get(tx["from_user_id"])
        to_user = users_by_id.get(tx["to_user_id"])
        from_name = (
            getattr(from_user, "first_name", f"User {tx['from_user_id']}")
            if from_user
            else f"User {tx['from_user_id']}"
        )
        to_name = (
            getattr(to_user, "first_name", f"User {tx['to_user_id']}")
            if to_user
            else f"User {tx['to_user_id']}"
        )
        amount_formatted = f"{tx["amount"] / 100:.2f}"

        lines.append(
            f"• **{from_name}** should pay **{to_name}** **${amount_formatted}**"
        )

    return (
        "🤝 **Suggested Payments to Settle Up:**\n"
        + "\n".join(lines)
        + "\n\n"
        + "*To log a payment, use:* `/payback @recipient <amount>` or tap the checkmark buttons below."
    )


def parse_payback_message(text: str) -> Dict[str, Any]:
    """
    Parses a /payback command to extract direct payment details.

    Expected formats:
    - /payback @recipient <amount>
    - /payback @payer @recipient <amount>

    Examples:
    - /payback @Alice 10 -> Payer: None (default sender), Payee: Alice, Amount: 1000
    - /payback @Bob @Alice 10 -> Payer: Bob, Payee: Alice, Amount: 1000

    :param text: The raw text of the message.
    :return: A dictionary containing:
             - 'payer_username': Username of the payer (lowercase, no @), or None
             - 'payee_username': Username of the payee (lowercase, no @)
             - 'amount': Amount in cents (int)
             - 'error': Error message string if parsing fails
    """
    cleaned_text = re.sub(r"^/payback(?:\s+|$)", "", text, flags=re.IGNORECASE).strip()

    mentions: List[Dict[str, Any]] = []
    for match in re.finditer(r"@(\w+)", cleaned_text):
        mentions.append(
            {
                "username": match.group(1).lower(),
                "start": match.start(),
                "end": match.end(),
            }
        )

    amount_match = re.search(r"\b(\d+(?:\.\d{1,2})?)\b", cleaned_text)
    if not amount_match:
        return {"error": "No valid amount found in the message."}

    amount_str = amount_match.group(1)

    if "." in amount_str:
        parts = amount_str.split(".")
        dollars = int(parts[0])
        cents_part = parts[1]
        cents = int(cents_part) * 10 if len(cents_part) == 1 else int(cents_part)
        amount_cents = dollars * 100 + cents
    else:
        amount_cents = int(amount_str) * 100

    if len(mentions) == 1:
        payer = None
        payee = mentions[0]["username"]
    elif len(mentions) >= 2:
        payer = mentions[0]["username"]
        payee = mentions[1]["username"]
    else:
        return {"error": "Must mention at least the recipient (payee) of the payback."}

    return {
        "payer_username": payer,
        "payee_username": payee,
        "amount": amount_cents,
    }


def generate_history_summary(transactions: List[Dict[str, Any]]) -> str:
    """
    Formats recent transactions (expenses and payments) into a Markdown string.
    """
    if not transactions:
        return "ℹ️ No recent transactions found in this group."

    lines = []
    for i, tx in enumerate(transactions, 1):
        t_type = tx["type"]
        obj = tx["obj"]
        amount_formatted = f"{obj.amount / 100:.2f}"

        if t_type == "expense":
            payer_name = getattr(obj.payer, "first_name", f"User {obj.payer_id}")
            desc = f" for '{obj.description}'" if obj.description else ""
            lines.append(
                f"{i}. 💸 **Expense:** **{payer_name}** paid **${amount_formatted}**{desc}"
            )
        elif t_type == "payment":
            payer_name = getattr(obj.payer, "first_name", f"User {obj.payer_id}")
            payee_name = getattr(obj.payee, "first_name", f"User {obj.payee_id}")
            lines.append(
                f"{i}. 🤝 **Payment:** **{payer_name}** paid **{payee_name}** **${amount_formatted}**"
            )

    return "📜 **Recent Group History:**\n" + "\n".join(lines)
