"""Keyboards for interactive ticket claiming and splitting."""

from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from ..receipt.pending_store import PendingTicketSession


class TicketKeyboardBuilder:
    """Builds inline keyboards for interactive ticket splitting."""

    @classmethod
    def build_main_ticket_keyboard(cls, token: str) -> InlineKeyboardMarkup:
        """Main bottom action bar below the ticket message."""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="👥 Assign Other...", callback_data=f"tkt:asgn:{token}"
                    ),
                    InlineKeyboardButton(
                        text="🏁 Finish & Split", callback_data=f"tkt:fin:{token}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="✕ Cancel Ticket", callback_data=f"tkt:cancel:{token}"
                    )
                ],
            ]
        )

    @classmethod
    def build_person_selector_keyboard(
        cls, session: PendingTicketSession, members: list[Any]
    ) -> InlineKeyboardMarkup:
        """Show group members and registered external guests to pick who to assign items for."""
        rows = []
        current_row = []

        # 1. Group members
        for m in members:
            name = getattr(m, "first_name", None) or f"User {getattr(m, 'id', '')}"
            uid = getattr(m, "telegram_id", getattr(m, "id", None))
            btn = InlineKeyboardButton(
                text=f"👤 {name}",
                callback_data=f"tkt:psel:{session.token}:tg:{uid}",
            )
            current_row.append(btn)
            if len(current_row) == 2:
                rows.append(current_row)
                current_row = []
        if current_row:
            rows.append(current_row)
            current_row = []

        # 2. Known external participants
        known_ext = session.get_known_external_participants()
        for p in known_ext:
            btn = InlineKeyboardButton(
                text=f"👤 {p.display_name} (ext)",
                callback_data=f"tkt:psel:{session.token}:{p.participant_key}",
            )
            current_row.append(btn)
            if len(current_row) == 2:
                rows.append(current_row)
                current_row = []
        if current_row:
            rows.append(current_row)

        # 3. Add new external guest
        rows.append(
            [
                InlineKeyboardButton(
                    text="➕ New External Guest...",
                    callback_data=f"tkt:asgn_new:{session.token}",
                )
            ]
        )

        # 4. Back to ticket
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬅️ Back to Ticket",
                    callback_data=f"tkt:back:{session.token}",
                )
            ]
        )
        return InlineKeyboardMarkup(rows)

    @classmethod
    def build_person_checklist_keyboard(
        cls, session: PendingTicketSession, participant_key: str
    ) -> InlineKeyboardMarkup:
        """Show full receipt items list as a checklist (◻️/☑️) for the selected participant."""
        from ..receipt.formatter import format_price

        rows = []
        currency = session.receipt.currency
        for it in session.items:
            is_claimed = participant_key in it.participants
            icon = "☑️" if is_claimed else "◻️"
            price_str = format_price(it.price, currency)
            btn_text = f"{icon} {it.item_index + 1}. {it.name[:14]} ({price_str})"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=btn_text,
                        callback_data=f"tkt:ptog:{session.token}:{participant_key}:{it.item_index}",
                    )
                ]
            )

        rows.append(
            [
                InlineKeyboardButton(
                    text="💾 Done / Save",
                    callback_data=f"tkt:back:{session.token}",
                ),
                InlineKeyboardButton(
                    text="⬅️ Change Person",
                    callback_data=f"tkt:asgn:{session.token}",
                ),
            ]
        )
        return InlineKeyboardMarkup(rows)

    @classmethod
    def build_item_selector_keyboard(
        cls, session: PendingTicketSession
    ) -> InlineKeyboardMarkup:
        """Show items to pick which one to assign a member to (legacy compat)."""
        rows = []
        current_row = []
        for it in session.items:
            label = f"{it.item_index + 1}. {it.name[:14]}"
            btn = InlineKeyboardButton(
                text=label,
                callback_data=f"tkt:asgn_itm:{session.token}:{it.item_index}",
            )
            current_row.append(btn)
            if len(current_row) == 2:
                rows.append(current_row)
                current_row = []
        if current_row:
            rows.append(current_row)

        rows.append(
            [
                InlineKeyboardButton(
                    text="⬅️ Back to Ticket", callback_data=f"tkt:back:{session.token}"
                )
            ]
        )
        return InlineKeyboardMarkup(rows)

    @classmethod
    def build_member_selector_keyboard(
        cls,
        token: str,
        item_idx: int,
        members: list[Any],
        _item_name: str | None = None,
    ) -> InlineKeyboardMarkup:
        """Show members to assign to a chosen item."""
        rows = []
        current_row = []
        for m in members:
            name = getattr(m, "first_name", f"User {m.id}")
            btn = InlineKeyboardButton(
                text=f"👤 {name}",
                callback_data=f"tkt:asgn_usr:{token}:{item_idx}:{m.id}",
            )
            current_row.append(btn)
            if len(current_row) == 2:
                rows.append(current_row)
                current_row = []
        if current_row:
            rows.append(current_row)

        rows.append(
            [
                InlineKeyboardButton(
                    text="➕ Add External Name",
                    callback_data=f"tkt:asgn_new:{token}:{item_idx}",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬅️ Back to Items", callback_data=f"tkt:asgn:{token}"
                )
            ]
        )
        return InlineKeyboardMarkup(rows)

    @classmethod
    def build_split_confirmation_keyboard(cls, token: str) -> InlineKeyboardMarkup:
        """Show confirmation actions after calculating split."""
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="💳 Record to Ledger",
                        callback_data=f"tkt:record:{token}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Back to Ticket", callback_data=f"tkt:back:{token}"
                    )
                ],
            ]
        )
