import datetime
import re
from typing import Optional, List, Dict, Any, Tuple


def _parse_amount_to_cents(amount_str: str) -> Optional[int]:
    """Parse a numeric string (integer or up to 2 decimals) into integer cents."""
    match = re.fullmatch(r"(\d+(?:\.\d{1,2})?)", amount_str)
    if not match:
        return None
    val = match.group(1)
    if "." in val:
        parts = val.split(".")
        dollars = int(parts[0])
        cents_part = parts[1]
        cents = int(cents_part) * 10 if len(cents_part) == 1 else int(cents_part[:2])
        return dollars * 100 + cents
    return int(val) * 100


def _parse_user_token(token: str) -> Optional[Tuple[str, Optional[int]]]:
    """
    Parses a user token like '@alice', '@bob:30', 'me', 'me:25.50'.
    Returns (username_or_me, amount_in_cents_or_none).
    """
    token = token.strip().rstrip(",")
    match = re.fullmatch(
        r"(?:@(\w+)|(me))(?::(\d+(?:\.\d{1,2})?))?", token, re.IGNORECASE
    )
    if not match:
        return None
    username = (match.group(1) or match.group(2)).lower()
    amount_str = match.group(3)
    amount = _parse_amount_to_cents(amount_str) if amount_str else None
    return username, amount


def parse_pay_message(text: str) -> Dict[str, Any]:
    """
    Parses a /pay command message to extract expense details.

    Supported Syntax:
    - /pay <amount> [for <description>] [by <payer_spec>] [split <split_spec>] [on <date>]

    Clauses can appear in any order. Quotes around <description> are optional unless
    it contains reserved keywords (e.g. /pay 50 for "Dinner with friends" by @Alice).

    Payer specs:
    - Omitted: Sender paid 100%.
    - by @Alice: Alice paid 100%.
    - by @Alice @Bob: Equal split between Alice and Bob.
    - by @Alice:30 @Bob:20: Custom amounts paid.
    - 'me' keyword can be used to refer to the sender.

    Split specs:
    - Omitted: Split equally among all group members.
    - split @Bob @Charlie: Split equally between Bob and Charlie.
    - split @Bob:20 @Charlie:30: Custom split shares.
    - split except @Dave: Split among all members except Dave.

    Date specs:
    - on YYYY-MM-DD, on today, on yesterday.

    Legacy shorthand formats (e.g. /pay @Alice 50 for Dinner) are also fully supported.

    :param text: The raw text of the message.
    :return: A dictionary containing:
             - 'payer_username': Primary/single payer username (lowercase, no @), or None
             - 'payers': Dict[str, int] mapping username/me to cents paid
             - 'amount': Total amount in cents (int)
             - 'description': Description string, or None
             - 'split_spec': Dict containing split configuration
             - 'participants': List of participant usernames (for backwards compatibility)
             - 'expense_date': Optional[datetime.date]
             - 'error': Error message string if parsing fails
    """
    # 1. Strip the /pay command prefix
    cleaned_text = re.sub(r"^/pay(?:\s+|$)", "", text, flags=re.IGNORECASE).strip()
    if not cleaned_text:
        return {"error": "No valid amount found in the message."}

    # 2. Extract quoted descriptions to avoid keyword collision inside strings
    placeholders: Dict[str, str] = {}

    def replace_quoted(m: re.Match) -> str:
        key = f"__QUOTED_DESC_{len(placeholders)}__"
        placeholders[key] = m.group(2)
        return f"for {key}"

    cleaned_text = re.sub(
        r"\bfor\s+([\"'])(.*?)\1", replace_quoted, cleaned_text, flags=re.IGNORECASE
    )

    # 3. Identify keyword clause boundaries: for, by, split, among, on, or 'with' followed by mention/me
    kw_regex = re.compile(
        r"\b(for|by|split|among|on)\b|\bwith\b(?=\s+(?:@|me\b))", re.IGNORECASE
    )
    matches = list(kw_regex.finditer(cleaned_text))

    clauses: Dict[str, str] = {}
    if matches:
        prefix_text = cleaned_text[: matches[0].start()].strip()
        for i, m in enumerate(matches):
            kw = m.group(1) or "split"  # 'with' maps to 'split'
            kw = kw.lower()
            if kw == "among":
                kw = "split"
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned_text)
            clause_content = cleaned_text[start:end].strip()
            clauses[kw] = clause_content
    else:
        prefix_text = cleaned_text

    # 4. Parse Date Clause ('on')
    expense_date: Optional[datetime.date] = None
    if "on" in clauses:
        on_raw = clauses["on"].strip().lower()
        if on_raw == "today":
            expense_date = datetime.date.today()
        elif on_raw == "yesterday":
            expense_date = datetime.date.today() - datetime.timedelta(days=1)
        else:
            try:
                expense_date = datetime.date.fromisoformat(on_raw)
            except ValueError:
                return {
                    "error": (
                        f"Invalid date format '{clauses['on']}'. "
                        "Expected YYYY-MM-DD, 'today', or 'yesterday'."
                    )
                }

    # 5. Parse Split Clause ('split')
    split_spec: Dict[str, Any] = {"mode": "all", "participants": []}
    if "split" in clauses:
        split_raw = clauses["split"].strip()
        exc_match = re.match(
            r"^(?:all\s+)?except\s+(.*)$", split_raw, flags=re.IGNORECASE
        )
        if exc_match:
            exc_tokens = exc_match.group(1).split()
            excluded = []
            for tok in exc_tokens:
                parsed_tok = _parse_user_token(tok)
                if not parsed_tok:
                    return {"error": f"Invalid username '{tok}' in 'except' split."}
                excluded.append(parsed_tok[0])
            split_spec = {"mode": "except", "excluded": excluded, "participants": []}
        elif split_raw.lower() in ("all", "everyone"):
            split_spec = {"mode": "all", "participants": []}
        else:
            tokens = split_raw.split()
            shares: Dict[str, Optional[int]] = {}
            has_custom_shares = False
            participants_list: List[str] = []
            for tok in tokens:
                parsed_tok = _parse_user_token(tok)
                if not parsed_tok:
                    return {
                        "error": f"Invalid participant token '{tok}' in 'split' clause."
                    }
                username, share_amt = parsed_tok
                participants_list.append(username)
                shares[username] = share_amt
                if share_amt is not None:
                    has_custom_shares = True

            if has_custom_shares:
                split_spec = {
                    "mode": "custom",
                    "shares": shares,
                    "participants": participants_list,
                }
            else:
                split_spec = {
                    "mode": "subset",
                    "participants": participants_list,
                }

    # 6. Parse Description Clause ('for')
    description: Optional[str] = None
    if "for" in clauses:
        for_raw = clauses["for"].strip()
        # Restore quoted description if present
        for placeholder, original in placeholders.items():
            if placeholder in for_raw:
                for_raw = for_raw.replace(placeholder, original)
                description = for_raw.strip()
                break

        if description is None:
            # Check for legacy participant syntax: /pay 50 for @Bob @Charlie
            tokens = for_raw.split()
            all_mentions = bool(tokens) and all(
                re.fullmatch(r"@\w+", t) for t in tokens
            )
            if all_mentions and "split" not in clauses:
                legacy_participants = [t.lstrip("@").lower() for t in tokens]
                split_spec = {
                    "mode": "subset",
                    "participants": legacy_participants,
                }
                description = None
            else:
                # Description with potential inline mentions (legacy: /pay 12.50 for lunch @Bob)
                mentions_in_for = [m.lower() for m in re.findall(r"@(\w+)", for_raw)]
                desc_cleaned = re.sub(r"@\w+", "", for_raw).strip()
                desc_cleaned = re.sub(r"\s+", " ", desc_cleaned)
                description = desc_cleaned if desc_cleaned else None
                if (
                    mentions_in_for
                    and "split" not in clauses
                    and not split_spec.get("participants")
                ):
                    split_spec = {
                        "mode": "subset",
                        "participants": mentions_in_for,
                    }

    # 7. Parse Raw Payers ('by')
    raw_payers: List[Tuple[str, Optional[int]]] = []
    if "by" in clauses:
        by_tokens = clauses["by"].split()
        for tok in by_tokens:
            parsed_tok = _parse_user_token(tok)
            if not parsed_tok:
                return {"error": f"Invalid payer token '{tok}' in 'by' clause."}
            raw_payers.append(parsed_tok)

    # 8. Resolve Numeric Amount and Legacy Payer from Prefix
    amount_cents: Optional[int] = None
    amt_match = re.search(r"\b(\d+(?:\.\d{1,2})?)\b", prefix_text)
    if amt_match:
        amount_cents = _parse_amount_to_cents(amt_match.group(1))
        # Check for legacy payer mention before amount in prefix: e.g. /pay @Alice 50 for Dinner
        if not raw_payers:
            prefix_before_amt = prefix_text[: amt_match.start()]
            payer_match = re.search(r"@(\w+)", prefix_before_amt)
            if payer_match:
                legacy_payer = payer_match.group(1).lower()
                raw_payers = [(legacy_payer, None)]

    # If amount was not in prefix, try inferring from custom payer amounts or custom splits
    if amount_cents is None:
        if raw_payers and all(a is not None for _, a in raw_payers):
            amount_cents = sum(a for _, a in raw_payers if a is not None)
        elif split_spec.get("mode") == "custom" and all(
            a is not None for a in split_spec.get("shares", {}).values()
        ):
            amount_cents = sum(
                a for a in split_spec["shares"].values() if a is not None
            )
        else:
            return {"error": "No valid amount found in the message."}

    if amount_cents <= 0:
        return {"error": "Amount must be greater than zero."}

    # 9. Finalize Payers and Distribute Amounts
    payers: Dict[str, int] = {}
    if not raw_payers:
        payers = {"me": amount_cents}
        payer_username = None
    else:
        specified_sum = sum(a for _, a in raw_payers if a is not None)
        unspecified = [u for u, a in raw_payers if a is None]

        if not unspecified:
            if specified_sum != amount_cents:
                return {
                    "error": (
                        f"Sum of payer amounts (${specified_sum / 100:.2f}) "
                        f"does not match total expense amount (${amount_cents / 100:.2f})."
                    )
                }
            payers = {u: a for u, a in raw_payers if a is not None}
        else:
            if specified_sum > amount_cents:
                return {
                    "error": (
                        f"Specified payer amounts (${specified_sum / 100:.2f}) "
                        f"exceed total expense amount (${amount_cents / 100:.2f})."
                    )
                }
            remaining = amount_cents - specified_sum
            unspecified_shares = split_amount_equally(remaining, len(unspecified))
            idx = 0
            for u, a in raw_payers:
                if a is not None:
                    payers[u] = a
                else:
                    payers[u] = unspecified_shares[idx]
                    idx += 1

        # Single payer backward compatibility
        if len(payers) == 1:
            first_user = next(iter(payers))
            payer_username = None if first_user == "me" else first_user
        else:
            payer_username = None

    # 10. Finalize Custom Split Shares
    if split_spec.get("mode") == "custom":
        shares = split_spec["shares"]
        specified_sum = sum(a for a in shares.values() if a is not None)
        unspecified = [u for u, a in shares.items() if a is None]

        if not unspecified:
            if specified_sum != amount_cents:
                return {
                    "error": (
                        f"Sum of split amounts (${specified_sum / 100:.2f}) "
                        f"does not match total expense amount (${amount_cents / 100:.2f})."
                    )
                }
        else:
            if specified_sum > amount_cents:
                return {
                    "error": (
                        f"Specified split amounts (${specified_sum / 100:.2f}) "
                        f"exceed total expense amount (${amount_cents / 100:.2f})."
                    )
                }
            remaining = amount_cents - specified_sum
            unspecified_shares = split_amount_equally(remaining, len(unspecified))
            idx = 0
            for u in list(shares.keys()):
                if shares[u] is None:
                    shares[u] = unspecified_shares[idx]
                    idx += 1

    # Populate top-level participants list for backwards compatibility
    participants = list(split_spec.get("participants", []))

    return {
        "payer_username": payer_username,
        "payers": payers,
        "amount": amount_cents,
        "participants": participants,
        "description": description,
        "split_spec": split_spec,
        "expense_date": expense_date,
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
        amount_formatted = f"{tx['amount'] / 100:.2f}"

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
            if getattr(obj, "payers", None) and len(obj.payers) > 1:
                payer_parts = [
                    f"{p.user.first_name} (${p.amount / 100:.2f})"
                    for p in obj.payers
                    if p.user
                ]
                payer_str = (
                    ", ".join(payer_parts) if payer_parts else "Multiple members"
                )
            elif (
                getattr(obj, "payers", None)
                and len(obj.payers) == 1
                and obj.payers[0].user
            ):
                payer_str = obj.payers[0].user.first_name
            elif getattr(obj, "payer", None) and obj.payer:
                payer_str = obj.payer.first_name
            else:
                payer_str = f"User {obj.payer_id}"

            desc = f" for '{obj.description}'" if obj.description else ""
            date_str = (
                f" on {obj.expense_date.isoformat()}"
                if getattr(obj, "expense_date", None)
                else ""
            )
            lines.append(
                f"{i}. 💸 **Expense:** **{payer_str}** paid **${amount_formatted}**{desc}{date_str}"
            )
        elif t_type == "payment":
            payer_name = getattr(obj.payer, "first_name", f"User {obj.payer_id}")
            payee_name = getattr(obj.payee, "first_name", f"User {obj.payee_id}")
            lines.append(
                f"{i}. 🤝 **Payment:** **{payer_name}** paid **{payee_name}** **${amount_formatted}**"
            )

    return "📜 **Recent Group History:**\n" + "\n".join(lines)
