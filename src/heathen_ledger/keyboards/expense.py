from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..models import Expense


class ExpenseKeyboardBuilder:
    """Builds inline keyboards for expenses and paybacks."""

    @classmethod
    def build_expense_undo_keyboard(
        cls, expense_id: int, creator_id: int
    ) -> InlineKeyboardMarkup:
        """Build inline keyboard containing a single Undo button for an expense."""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="🗑️ Undo",
                        callback_data=f"undo:expense:{expense_id}:{creator_id}",
                    )
                ]
            ]
        )

    @classmethod
    def build_split_toggle_keyboard(
        cls, expense: Expense, group_members: list[Any], creator_id: int
    ) -> InlineKeyboardMarkup:
        """Build the inline keyboard with toggle buttons for each group member and an Undo button."""
        participant_ids = {s.user_id for s in expense.splits}
        sorted_members = sorted(group_members, key=lambda m: m.first_name)

        keyboard = []
        row = []
        for member in sorted_members:
            is_p = member.id in participant_ids
            prefix = "✅" if is_p else "❌"
            button = InlineKeyboardButton(
                text=f"{prefix} {member.first_name}",
                callback_data=f"pay_toggle:{expense.id}:{member.id}:{creator_id}",
            )
            row.append(button)
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        keyboard.append(
            [
                InlineKeyboardButton(
                    text="🗑️ Undo",
                    callback_data=f"undo:expense:{expense.id}:{creator_id}",
                )
            ]
        )
        return InlineKeyboardMarkup(keyboard)

    @classmethod
    def build_payback_undo_keyboard(
        cls, payment_id: int, creator_id: int
    ) -> InlineKeyboardMarkup:
        """Build inline keyboard containing a single Undo button for a payment."""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="🗑️ Undo",
                        callback_data=f"undo:payment:{payment_id}:{creator_id}",
                    )
                ]
            ]
        )
