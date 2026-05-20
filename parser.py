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
