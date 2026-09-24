from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..formatters import format_cents


class SettlementKeyboardBuilder:
    """Builds interactive inline buttons for suggested settlement payments."""

    @classmethod
    def build_settle_keyboard(
        cls, transactions: list[dict[str, Any]], users_by_id: dict[int, Any]
    ) -> InlineKeyboardMarkup | None:
        """Build inline confirmation buttons for suggested payback transactions."""
        if not transactions:
            return None

        keyboard = []
        for tx in transactions:
            from_db_user = users_by_id.get(tx["from_user_id"])
            to_db_user = users_by_id.get(tx["to_user_id"])
            from_name = (
                from_db_user.first_name
                if from_db_user
                else f"User {tx['from_user_id']}"
            )
            to_name = (
                to_db_user.first_name if to_db_user else f"User {tx['to_user_id']}"
            )
            amount_formatted = format_cents(tx["amount"])

            button_text = f"✅ {from_name} paid {to_name} {amount_formatted}"
            callback_data = (
                f"settle:{tx['from_user_id']}:{tx['to_user_id']}:{tx['amount']}"
            )
            keyboard.append(
                [InlineKeyboardButton(text=button_text, callback_data=callback_data)]
            )
        return InlineKeyboardMarkup(keyboard)
