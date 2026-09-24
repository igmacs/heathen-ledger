"""Presentation layer: formatting monetary amounts, balances, settlements, history, and expenses."""

import html
from typing import Any


def format_cents(cents: int, currency: str = "$") -> str:
    """Format an integer amount of cents into a currency string (e.g. 1250 -> '$12.50')."""
    if cents < 0:
        return f"-{currency}{abs(cents) / 100:.2f}"
    return f"{currency}{cents / 100:.2f}"


def generate_balances_summary(
    balances: dict[int, int], users_by_id: dict[int, Any]
) -> str:
    """Formats the net balances of group members into a human-readable Markdown string."""
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
        amount_str = format_cents(abs(balance))

        if balance > 0:
            lines.append(f"• **{name}** is owed **{amount_str}**")
        elif balance < 0:
            lines.append(f"• **{name}** owes **{amount_str}**")
        else:
            lines.append(f"• **{name}** is settled up")

    return "📊 **Current Net Balances:**\n" + "\n".join(lines)


def generate_settlements_summary(
    transactions: list[dict[str, Any]], users_by_id: dict[int, Any]
) -> str:
    """Formats the list of suggested payments into a human-readable Markdown string."""
    if not transactions:
        return (
            "✅ **Everyone is fully settled up! No transactions needed.**\n\n"
            "💡 Run `/close` to close this ledger and leave the group."
        )

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
        amount_formatted = format_cents(tx["amount"])

        lines.append(
            f"• **{from_name}** should pay **{to_name}** **{amount_formatted}**"
        )

    return (
        "🤝 **Suggested Payments to Settle Up:**\n"
        + "\n".join(lines)
        + "\n\n"
        + "*To log a payment, use:* `/payback @recipient <amount>` or tap the checkmark buttons below."
    )


def generate_history_summary(transactions: list[dict[str, Any]]) -> str:
    """Formats recent transactions (expenses and payments) into a Markdown string."""
    if not transactions:
        return "ℹ️ No recent transactions found in this group."

    lines = []
    for i, tx in enumerate(transactions, 1):
        t_type = tx["type"]
        obj = tx["obj"]
        amount_formatted = format_cents(obj.amount)

        if t_type == "expense":
            if getattr(obj, "payers", None) and len(obj.payers) > 1:
                payer_parts = [
                    f"{p.user.first_name} ({format_cents(p.amount)})"
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
                payer_str = "Unknown"

            desc = f" for '{obj.description}'" if obj.description else ""
            date_str = (
                f" on {obj.expense_date.isoformat()}"
                if getattr(obj, "expense_date", None)
                else ""
            )
            lines.append(
                f"{i}. 💸 **Expense:** **{payer_str}** paid **{amount_formatted}**{desc}{date_str}"
            )
        elif t_type == "payment":
            payer_name = getattr(obj.payer, "first_name", f"User {obj.payer_id}")
            payee_name = getattr(obj.payee, "first_name", f"User {obj.payee_id}")
            lines.append(
                f"{i}. 🤝 **Payment:** **{payer_name}** paid **{payee_name}** **{amount_formatted}**"
            )

    return "📜 **Recent Group History:**\n" + "\n".join(lines)


def generate_history_rich_html(transactions: list[dict[str, Any]]) -> str:
    """Formats recent transactions into Telegram Rich HTML with embedded delete buttons beside each entry."""
    if not transactions:
        return "<p>ℹ️ No recent transactions found in this group.</p>"

    lines = ["<p><b>📜 Recent Group History:</b></p>"]
    for i, tx in enumerate(transactions, 1):
        t_type = tx["type"]
        obj = tx["obj"]
        amount_formatted = format_cents(obj.amount)
        callback_data = f"hist_del:{t_type}:{obj.id}"
        delete_btn = f'<tg-button type="callback_data" style="danger" data="{callback_data}">🗑️</tg-button>'

        if t_type == "expense":
            if getattr(obj, "payers", None) and len(obj.payers) > 1:
                payer_parts = [
                    f"{html.escape(p.user.first_name)} ({format_cents(p.amount)})"
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
                payer_str = html.escape(obj.payers[0].user.first_name)
            elif getattr(obj, "payer", None) and obj.payer:
                payer_str = html.escape(obj.payer.first_name)
            else:
                payer_str = "Unknown"

            desc = f" for '{html.escape(obj.description)}'" if obj.description else ""
            date_str = (
                f" on {html.escape(obj.expense_date.isoformat())}"
                if getattr(obj, "expense_date", None)
                else ""
            )
            lines.append(
                f"<p>{i}. 💸 <b>Expense:</b> <b>{payer_str}</b> paid <b>{amount_formatted}</b>{desc}{date_str} {delete_btn}</p>"
            )
        elif t_type == "payment":
            payer_raw = getattr(obj.payer, "first_name", f"User {obj.payer_id}")
            payee_raw = getattr(obj.payee, "first_name", f"User {obj.payee_id}")
            payer_name = html.escape(payer_raw)
            payee_name = html.escape(payee_raw)
            lines.append(
                f"<p>{i}. 🤝 <b>Payment:</b> <b>{payer_name}</b> paid <b>{payee_name}</b> <b>{amount_formatted}</b> {delete_btn}</p>"
            )

    return "\n".join(lines)


def generate_expense_reply_text(expense: Any) -> str:
    """Format the expense split summary."""
    amount_formatted = format_cents(expense.amount)
    desc_str = f" for '{expense.description}'" if expense.description else ""

    # Sort the splits by the user's first_name to keep the display order stable
    sorted_splits = sorted(expense.splits, key=lambda s: s.user.first_name)
    participants = [s.user for s in sorted_splits]
    parts_str = ", ".join([u.first_name for u in participants])

    # Format Payers
    if expense.payers and len(expense.payers) > 1:
        payer_lines = []
        for p in expense.payers:
            payer_lines.append(f"  - {p.user.first_name}: {format_cents(p.amount)}")
        paid_by_str = "• **Paid by:**\n" + "\n".join(payer_lines)
    elif expense.payers and len(expense.payers) == 1:
        paid_by_str = f"• **Paid by:** {expense.payers[0].user.first_name}"
    elif expense.payer:
        paid_by_str = f"• **Paid by:** {expense.payer.first_name}"
    else:
        paid_by_str = "• **Paid by:** Unknown"

    date_line = (
        f"• **Date:** {expense.expense_date.isoformat()}\n"
        if expense.expense_date
        else ""
    )

    reply_text = (
        f"✅ Recorded expense:\n"
        f"{paid_by_str}\n"
        f"• **Amount:** {amount_formatted}{desc_str}\n"
        f"{date_line}"
        f"• **Split between:** {parts_str}\n"
    )

    if len(sorted_splits) > 1:
        reply_text += "• **Shares:**\n"
        for s in sorted_splits:
            reply_text += f"  - {s.user.first_name}: {format_cents(s.amount)}\n"

    return reply_text
