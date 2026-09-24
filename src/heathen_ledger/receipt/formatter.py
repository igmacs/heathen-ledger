"""Rich HTML and Markdown formatters for interactive ticket splitting."""

import html
from typing import Any

from .pending_store import PendingTicketSession


def format_price(amount: float, currency: str | None = None) -> str:
    """Format an amount with currency symbol or code."""
    if not currency:
        return f"{amount:.2f}"
    if currency in ("$", "£", "¥"):
        return f"{currency}{amount:.2f}"
    return f"{amount:.2f} {currency}"


def format_ticket_rich_html(session: PendingTicketSession) -> str:
    """Format an interactive ticket session into Telegram Bot API 10.3+ Rich HTML."""
    currency = session.receipt.currency
    curr_str = f" ({currency})" if currency else ""
    merchant = html.escape(session.receipt.merchant or "Receipt")

    lines = []
    lines.append(f"<p>🧾 <b>{merchant}</b>{curr_str}</p>")
    lines.append(
        "<p>Tap <b>[+Me]</b> to claim or share an item. Tap <b>[✅]</b> when an item is fully claimed.</p>"
    )

    for idx, it in enumerate(session.items):
        it_name = html.escape(it.name)
        price_str = format_price(it.price, currency)
        token = session.token

        me_btn = f'<tg-button type="callback_data" data="tkt:m:{token}:{idx}">👤 +Me</tg-button>'

        if it.is_completed:
            done_btn = f'<tg-button type="callback_data" data="tkt:d:{token}:{idx}">↩️</tg-button>'
            line_body = f"<s>✅ {idx + 1}. {it_name} — {price_str}</s>"
        else:
            done_btn = f'<tg-button type="callback_data" data="tkt:d:{token}:{idx}">✅</tg-button>'
            line_body = f"{idx + 1}. {it_name} — {price_str}"

        # Badges for participants
        if it.participants:
            inits_str = html.escape(", ".join(it.initials_list))
            icon = "👤" if len(it.participants) == 1 else "👥"
            badge = f"<b>({icon} {inits_str})</b>"
        else:
            badge = "<i>(unclaimed)</i>" if not it.is_completed else ""

        btn_group = f"{me_btn} {done_btn}" if not it.is_completed else done_btn
        badge_str = f" {badge}" if badge else ""
        lines.append(f"<p>{line_body} {btn_group}{badge_str}</p>")

    # Totals summary
    summary_parts = []
    if session.receipt.subtotal is not None:
        summary_parts.append(
            f"• <b>Subtotal:</b> {format_price(session.receipt.subtotal, currency)}"
        )
    if session.receipt.tax is not None:
        summary_parts.append(
            f"• <b>Tax:</b> {format_price(session.receipt.tax, currency)}"
        )
    if session.receipt.tip is not None:
        summary_parts.append(
            f"• <b>Tip:</b> {format_price(session.receipt.tip, currency)}"
        )
    if session.receipt.total is not None:
        summary_parts.append(
            f"• <b>Total:</b> {format_price(session.receipt.total, currency)}"
        )

    if summary_parts:
        lines.append("<p>" + "  ".join(summary_parts) + "</p>")

    claimed_count = sum(1 for it in session.items if it.participants)
    total_items = len(session.items)
    lines.append(
        f"<p>📊 <b>Progress:</b> {claimed_count}/{total_items} items claimed</p>"
    )

    return "\n".join(lines)


def format_ticket_split_summary(
    session: PendingTicketSession,
    shares: dict[str, dict[str, Any]],
) -> str:
    """Format the calculated ticket split summary in Markdown."""
    currency = session.receipt.currency
    target_total = (
        session.receipt.total
        if session.receipt.total is not None
        else round(sum(it.price for it in session.items), 2)
    )
    formatted_total = format_price(target_total, currency)

    lines = [
        "🧾 *Bill Split Summary*",
        f"📍 *{session.receipt.merchant or 'Receipt'}* — Total: *{formatted_total}*",
        "",
    ]

    if not shares:
        lines.append("⚠️ _No items have been claimed yet._")
        return "\n".join(lines)

    for p in shares.values():
        name = p["display_name"]
        uname_str = f" (@{p['username']})" if p.get("username") else ""
        ext_str = " _(external)_" if p.get("is_external") else ""
        amt_str = format_price(p["total_share"], currency)

        details = []
        if p.get("items_subtotal"):
            details.append(f"items: {format_price(p['items_subtotal'], currency)}")
        if p.get("extra_fee_share"):
            details.append(f"fees/tax: {format_price(p['extra_fee_share'], currency)}")
        detail_str = f" _({', '.join(details)})_" if details else ""

        lines.append(f"• *{name}*{uname_str}{ext_str}: *{amt_str}*{detail_str}")

    lines.append("")
    lines.append("────────────────────")
    lines.append("Tap *Record to Ledger* to create this expense in group balances.")
    return "\n".join(lines)


def format_ticket_split_rich_html(
    session: PendingTicketSession,
    shares: dict[str, dict[str, Any]],
) -> str:
    """Format the calculated ticket split summary in Telegram Rich HTML."""
    currency = session.receipt.currency
    target_total = (
        session.receipt.total
        if session.receipt.total is not None
        else round(sum(it.price for it in session.items), 2)
    )
    formatted_total = format_price(target_total, currency)
    merchant = html.escape(session.receipt.merchant or "Receipt")

    lines = [
        "<p>🧾 <b>Bill Split Summary</b></p>",
        f"<p>📍 <b>{merchant}</b> — Total: <b>{formatted_total}</b></p>",
    ]

    if not shares:
        lines.append("<p>⚠️ <i>No items have been claimed yet.</i></p>")
        return "\n".join(lines)

    for p in shares.values():
        name = html.escape(p["display_name"])
        uname_str = f" (@{html.escape(p['username'])})" if p.get("username") else ""
        ext_str = " <i>(external)</i>" if p.get("is_external") else ""
        amt_str = format_price(p["total_share"], currency)

        details = []
        if p.get("items_subtotal"):
            details.append(f"items: {format_price(p['items_subtotal'], currency)}")
        if p.get("extra_fee_share"):
            details.append(f"fees/tax: {format_price(p['extra_fee_share'], currency)}")
        detail_str = f" <i>({', '.join(details)})</i>" if details else ""

        lines.append(
            f"<p>• <b>{name}</b>{uname_str}{ext_str}: <b>{amt_str}</b>{detail_str}</p>"
        )

    lines.append("<p>────────────────────</p>")
    lines.append(
        "<p>Tap <b>Record to Ledger</b> to create this expense in group balances.</p>"
    )
    return "\n".join(lines)
