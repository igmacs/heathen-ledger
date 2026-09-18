import logging
from typing import Optional, Tuple
from telegram import InlineKeyboardMarkup
from sqlalchemy.orm import Session

from ..parser import PayCommandParser, PaybackCommandParser
from ..formatters import (
    generate_expense_reply_text,
    generate_balances_summary,
    generate_settlements_summary,
    generate_history_summary,
    format_cents,
)
from ..keyboards import (
    ExpenseKeyboardBuilder,
    SettlementKeyboardBuilder,
    HistoryKeyboardBuilder,
)
from ..services import (
    ExpenseService,
    SettlementService,
    HistoryService,
    MemberRegistrationService,
)
from ..services.exceptions import UserNotFoundError, ValidationError

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """Executes bot ledger commands and returns formatted response text and UI keyboards."""

    @classmethod
    def execute(
        cls,
        command_str: str,
        chat_id: int,
        creator_id: int,
        creator_username: Optional[str],
        creator_first_name: Optional[str],
        session: Session,
        chat_title: Optional[str] = None,
    ) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
        """Execute a parsed or raw bot command string and return (reply_text, reply_markup)."""
        cmd_clean = command_str.strip()
        if not cmd_clean.startswith("/"):
            cmd_clean = f"/{cmd_clean}"

        cmd_parts = cmd_clean.split()
        cmd_name = cmd_parts[0].split("@")[0].lower()

        # Resolve sender and group
        sender, group = MemberRegistrationService.ensure_member_in_group(
            session=session,
            chat_id=chat_id,
            user_id=creator_id,
            username=creator_username,
            first_name=creator_first_name or f"User{creator_id}",
            chat_title=chat_title,
        )

        if cmd_name == "/pay":
            parsed = PayCommandParser.parse(cmd_clean)
            if "error" in parsed:
                return (
                    f"⚠️ Error parsing command: {parsed['error']}\n"
                    f"Usage: `/pay <amount> [for <description>] [by <payer(s)>] [split <participants>] [on <date>]`",
                    None,
                )
            try:
                expense = ExpenseService.record_expense(
                    session=session,
                    group=group,
                    sender=sender,
                    command=parsed,
                )
            except (UserNotFoundError, ValidationError) as e:
                return f"⚠️ {e}", None

            reply_text = generate_expense_reply_text(expense)
            reply_markup = ExpenseKeyboardBuilder.build_expense_undo_keyboard(
                expense_id=expense.id, creator_id=sender.id
            )
            return reply_text, reply_markup

        elif cmd_name == "/payback":
            parsed = PaybackCommandParser.parse(cmd_clean)
            if "error" in parsed:
                return (
                    f"⚠️ Error parsing command: {parsed['error']}\n"
                    f"Usage: `/payback [@payer] @recipient <amount>`",
                    None,
                )
            try:
                payment = ExpenseService.record_payback(
                    session=session,
                    group=group,
                    sender=sender,
                    command=parsed,
                )
            except (UserNotFoundError, ValidationError) as e:
                return f"⚠️ {e}", None

            amount_formatted = format_cents(payment.amount)
            reply_markup = ExpenseKeyboardBuilder.build_payback_undo_keyboard(
                payment.id, sender.id
            )
            reply_text = (
                f"✅ **Recorded payment:**\n"
                f"• **Paid by:** {payment.payer.first_name}\n"
                f"• **Paid to:** {payment.payee.first_name}\n"
                f"• **Amount:** {amount_formatted}"
            )
            return reply_text, reply_markup

        elif cmd_name == "/balances":
            if not group or not group.members:
                return (
                    "ℹ️ No transactions or members recorded for this group yet.",
                    None,
                )
            balances, _, users_by_id = (
                SettlementService.get_group_balances_and_settlements(session, group.id)
            )
            reply_text = generate_balances_summary(balances, users_by_id)
            return reply_text, None

        elif cmd_name == "/settle":
            if not group or not group.members:
                return (
                    "ℹ️ No transactions or members recorded for this group yet.",
                    None,
                )
            _, transactions, users_by_id = (
                SettlementService.get_group_balances_and_settlements(session, group.id)
            )
            reply_text = generate_settlements_summary(transactions, users_by_id)
            reply_markup = SettlementKeyboardBuilder.build_settle_keyboard(
                transactions, users_by_id
            )
            return reply_text, reply_markup

        elif cmd_name == "/history":
            if not group:
                return (
                    "ℹ️ No transactions or members recorded for this group yet.",
                    None,
                )
            txs = HistoryService.get_recent_transactions(session, group.id, limit=10)
            reply_text = generate_history_summary(txs)
            reply_markup = HistoryKeyboardBuilder.build_history_keyboard(txs)
            return reply_text, reply_markup

        else:
            return f"⚠️ Unsupported command from voice note: `{cmd_clean}`", None
