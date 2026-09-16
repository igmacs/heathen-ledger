from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class VoiceKeyboardBuilder:
    """Builds inline buttons for voice interpretation confirmation and rejection."""

    @classmethod
    def build_confirmation_keyboard(cls, token: str) -> InlineKeyboardMarkup:
        """Build confirm and reject buttons for an interpreted voice command."""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="✅ Confirm",
                        callback_data=f"voice:confirm:{token}",
                    ),
                    InlineKeyboardButton(
                        text="❌ Reject", callback_data=f"voice:reject:{token}"
                    ),
                ]
            ]
        )
