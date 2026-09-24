from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class HistoryKeyboardBuilder:
    """Builds interactive inline buttons for deleting recent transactions."""

    @classmethod
    def build_history_keyboard(
        cls, transactions: list[dict[str, Any]]
    ) -> InlineKeyboardMarkup | None:
        """Builds deletion buttons for recent transactions."""
        if not transactions:
            return None

        keyboard = []
        for i, tx in enumerate(transactions, 1):
            t_type = tx["type"]
            obj = tx["obj"]
            callback_data = f"hist_del:{t_type}:{obj.id}"
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=f"🗑️ Delete {i}", callback_data=callback_data
                    )
                ]
            )
        return InlineKeyboardMarkup(keyboard)
