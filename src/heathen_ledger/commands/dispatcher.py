import logging
from typing import Optional, Tuple
from telegram import InlineKeyboardMarkup
from sqlalchemy.orm import Session

from ..repositories import UserRepository, GroupRepository, PaymentRepository
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
from ..services import expense_service, settlement_service
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

        # Resolve group
        group_repo = GroupRepository(session)
        user_repo = UserRepository(session)

        group = group_repo.get_by_telegram_id(chat_id)
        if not group:
            group = group_repo.get_or_create(chat_id, chat_title)

        # Resolve sender
        sender = user_repo.get_by_telegram_id(creator_id)
        if not sender:
            sender = user_repo.get_or_create(
                telegram_id=creator_id,
                username=creator_username,
                first_name=creator_first_name or f"User{creator_id}",
            )
        user_repo.add_to_group(sender, group)

        if cmd_name == "/pay":
            parsed = PayCommandParser.parse(cmd_clean)
            if "error" in parsed:
                return (
                    f"⚠️ Error parsing command: {parsed['error']}\n"
                    f"Usage: `/pay <amount> [for <description>] [by <payer(s)>] [split <participants>] [on <date>]`",
                    None,
                )
            try:
                expense = expense_service.record_expense(
                    session=session,
                    group=group,
                    sender=sender,
                    command=parsed,
                )
            except (UserNotFoundError, ValidationError) as e:
                return f"⚠️ {e}", None

            reply_text = generate_expense_reply_text(expense)
            reply_markup = ExpenseKeyboardBuilder.build_split_toggle_keyboard(
                expense, group.members, sender.id
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
                payment = expense_service.record_payback(
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
                settlement_service.get_group_balances_and_settlements(session, group.id)
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
                settlement_service.get_group_balances_and_settlements(session, group.id)
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
            txs = PaymentRepository(session).get_recent_transactions(group.id, limit=10)
            reply_text = generate_history_summary(txs)
            reply_markup = HistoryKeyboardBuilder.build_history_keyboard(txs)
            return reply_text, reply_markup

        else:
            return f"⚠️ Unsupported command from voice note: `{cmd_clean}`", None
