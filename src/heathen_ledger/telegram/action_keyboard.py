from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class EphemeralActionKeyboardDecorator:
    """Decorates responses with 'Share to group' and 'Dismiss' action buttons."""

    @classmethod
    def has_dismiss_button(cls, reply_markup: Optional[InlineKeyboardMarkup]) -> bool:
        """Check if reply_markup already contains a button with dismiss callback_data."""
        if not reply_markup or not getattr(reply_markup, "inline_keyboard", None):
            return False
        for row in reply_markup.inline_keyboard:
            for btn in row:
                cb = getattr(btn, "callback_data", None)
                if cb and (cb == "dismiss" or cb.startswith("dismiss:")):
                    return True
        return False

    @classmethod
    def attach_action_buttons(
        cls,
        reply_markup: Optional[InlineKeyboardMarkup],
        token: Optional[str],
        can_share: bool,
        dismissible: bool,
    ) -> Optional[InlineKeyboardMarkup]:
        """Attach 'Share to group' and 'Dismiss' buttons to an existing keyboard."""
        action_buttons = []
        if can_share and token:
            action_buttons.append(
                InlineKeyboardButton(
                    "📢 Share to group", callback_data=f"persist:{token}"
                )
            )

        if dismissible and not cls.has_dismiss_button(reply_markup):
            cb_data = f"dismiss:{token}" if token else "dismiss"
            action_buttons.append(
                InlineKeyboardButton("✕ Dismiss", callback_data=cb_data)
            )

        if not action_buttons:
            return reply_markup

        if reply_markup is not None and getattr(reply_markup, "inline_keyboard", None):
            new_keyboard = [list(row) for row in reply_markup.inline_keyboard]
            new_keyboard.append(action_buttons)
            return InlineKeyboardMarkup(new_keyboard)
        else:
            return InlineKeyboardMarkup([action_buttons])
