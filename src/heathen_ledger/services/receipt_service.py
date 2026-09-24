"""Service layer for receipt photo parsing, interactive claiming, and itemization."""

import contextlib
import html
import logging
from typing import Any

from sqlalchemy.orm import Session
from telegram import Bot, InlineKeyboardMarkup, Message
from telegram.constants import ChatAction

from .. import crud
from ..keyboards.ticket import TicketKeyboardBuilder
from ..receipt import (
    PendingTicketSession,
    PendingTicketStore,
    Receipt,
    ReceiptImageDownloader,
    TicketParticipant,
    get_receipt_parser,
)
from ..receipt.formatter import (
    format_price,
    format_ticket_rich_html,
    format_ticket_split_rich_html,
    format_ticket_split_summary,
)
from ..repositories import GroupRepository, UserRepository
from .exceptions import ValidationError

logger = logging.getLogger(__name__)


class CommandDispatcher:
    """Proxy to prevent circular import between commands and services."""

    @staticmethod
    def execute(*args, **kwargs):
        from ..commands.dispatcher import CommandDispatcher as _CD

        return _CD.execute(*args, **kwargs)


class ReceiptService:
    """Service orchestrating receipt image downloading, OCR parsing, and interactive splitting."""

    _store = PendingTicketStore()

    @classmethod
    def get_store(cls) -> PendingTicketStore:
        """Return the backing PendingTicketStore."""
        return cls._store

    @classmethod
    def format_price(cls, amount: float, currency: str | None = None) -> str:
        """Format an amount with currency symbol or code."""
        return format_price(amount, currency)

    @classmethod
    def format_receipt_breakdown(cls, receipt: Receipt) -> str:
        """Format a parsed receipt into a human-readable Markdown summary."""
        lines = []
        header = "🧾 *Receipt Breakdown*"
        if receipt.merchant:
            header += f"\n📍 *{receipt.merchant}*"
        if receipt.date:
            header += f" _({receipt.date})_"
        lines.append(header)
        lines.append("")

        if not receipt.items:
            lines.append("⚠️ _No itemized lines could be detected on this receipt._")
            if receipt.total is not None:
                lines.append(
                    f"\n*Total:* {cls.format_price(receipt.total, receipt.currency)}"
                )
            return "\n".join(lines)

        expanded_items = receipt.expand_items()
        for idx, item in enumerate(expanded_items, 1):
            formatted_price = cls.format_price(item.price, receipt.currency)
            lines.append(f"{idx}. {item.name} — {formatted_price}")

        summary_lines = []
        if receipt.subtotal is not None:
            summary_lines.append(
                f"• *Subtotal:* {cls.format_price(receipt.subtotal, receipt.currency)}"
            )
        if receipt.tax is not None:
            summary_lines.append(
                f"• *Tax:* {cls.format_price(receipt.tax, receipt.currency)}"
            )
        if receipt.tip is not None:
            summary_lines.append(
                f"• *Tip:* {cls.format_price(receipt.tip, receipt.currency)}"
            )
        if receipt.total is not None:
            summary_lines.append(
                f"• *Total:* {cls.format_price(receipt.total, receipt.currency)}"
            )

        if summary_lines:
            lines.append("\n" + "─" * 20)
            lines.extend(summary_lines)

        return "\n".join(lines)

    @classmethod
    def create_ticket_session(
        cls,
        chat_id: int,
        creator_id: int | None,
        creator_name: str | None,
        receipt: Receipt,
        token: str | None = None,
    ) -> PendingTicketSession:
        """Create a new interactive ticket session and save it in store."""
        session = PendingTicketSession.create(
            chat_id=chat_id,
            creator_id=creator_id,
            creator_name=creator_name,
            receipt=receipt,
            token=token,
        )
        cls._store.store(session)
        return session

    @classmethod
    def get_session(cls, token: str) -> PendingTicketSession | None:
        """Retrieve an active ticket session by token."""
        return cls._store.get(token)

    @classmethod
    def pop_session(cls, token: str) -> PendingTicketSession | None:
        """Pop an active ticket session by token."""
        return cls._store.pop(token)

    @classmethod
    def clear_sessions(cls) -> None:
        """Clear all active sessions."""
        cls._store.clear()

    @classmethod
    def toggle_item_me(
        cls,
        token: str,
        item_idx: int,
        user_id: int,
        display_name: str,
        username: str | None = None,
        last_name: str | None = None,
    ) -> tuple[PendingTicketSession | None, bool]:
        """Toggle current user's claim on an item."""
        session = cls.get_session(token)
        if not session:
            return None, False
        added = session.toggle_participant(
            item_index=item_idx,
            user_id=user_id,
            display_name=display_name,
            username=username,
            last_name=last_name,
        )
        return session, added

    @classmethod
    def toggle_item_done(
        cls,
        token: str,
        item_idx: int,
    ) -> tuple[PendingTicketSession | None, bool]:
        """Toggle an item's completed/locked status."""
        session = cls.get_session(token)
        if not session:
            return None, False
        done = session.toggle_completed(item_idx)
        return session, done

    @classmethod
    def assign_group_member(
        cls,
        token: str,
        item_idx: int,
        user_id: int,
        display_name: str,
        username: str | None = None,
    ) -> PendingTicketSession | None:
        """Assign a known group member to an item."""
        session = cls.get_session(token)
        if not session:
            return None
        session.toggle_participant(
            item_index=item_idx,
            user_id=user_id,
            display_name=display_name,
            username=username,
        )
        return session

    @classmethod
    def assign_external_member(
        cls,
        token: str,
        item_idx: int,
        name: str,
    ) -> PendingTicketSession | None:
        """Assign an external non-group participant to an item."""
        session = cls.get_session(token)
        if not session:
            return None
        session.assign_external_participant(item_idx, name)
        return session

    @classmethod
    def register_external_participant(
        cls,
        token: str,
        name: str,
    ) -> tuple[PendingTicketSession | None, TicketParticipant | None]:
        """Register or retrieve an external guest in the ticket session."""
        session = cls.get_session(token)
        if not session:
            return None, None
        p = session.register_external_participant(name)
        return session, p

    @classmethod
    def toggle_participant_item(
        cls,
        token: str,
        participant_key: str,
        item_idx: int,
        participant: TicketParticipant | None = None,
    ) -> tuple[PendingTicketSession | None, bool]:
        """Toggle participation of a user/guest on an item by key."""
        session = cls.get_session(token)
        if not session:
            return None, False
        added = session.toggle_participant_by_key(
            item_index=item_idx,
            participant_key=participant_key,
            participant=participant,
        )
        return session, added

    @classmethod
    def build_person_selector_message(
        cls,
        token: str,
        db_session: Session,
    ) -> tuple[str | None, InlineKeyboardMarkup | None]:
        """Build message and keyboard to select who to assign items for."""
        session = cls.get_session(token)
        if not session:
            return None, None

        grp_repo = GroupRepository(db_session)
        group = grp_repo.get_by_telegram_id(session.chat_id)
        members = group.members if group and group.members else []

        rich_html = (
            "<p>👥 <b>Assign Items — Select Person</b></p>\n"
            "<p>Choose a group member or external guest to select their items:</p>"
        )
        keyboard = TicketKeyboardBuilder.build_person_selector_keyboard(
            session=session, members=members
        )
        return rich_html, keyboard

    @classmethod
    def build_person_checklist_message(
        cls,
        token: str,
        participant_key: str,
        participant_name: str | None = None,
    ) -> tuple[str | None, InlineKeyboardMarkup | None]:
        """Build message and checklist keyboard for a chosen participant."""
        session = cls.get_session(token)
        if not session:
            return None, None

        if not participant_name:
            if participant_key in session.external_participants:
                participant_name = session.external_participants[
                    participant_key
                ].display_name
            else:
                for it in session.items:
                    if participant_key in it.participants:
                        participant_name = it.participants[participant_key].display_name
                        break
        name = participant_name or participant_key
        safe_name = html.escape(name)
        ext_tag = " <i>(external)</i>" if participant_key.startswith("ext:") else ""

        rich_html = (
            f"<p>🧾 <b>Assign Items for: {safe_name}</b>{ext_tag}</p>\n"
            f"<p><i>Tap items below to toggle participation:</i></p>"
        )
        keyboard = TicketKeyboardBuilder.build_person_checklist_keyboard(
            session=session, participant_key=participant_key
        )
        return rich_html, keyboard

    @classmethod
    def build_ticket_rich_message(
        cls, token: str
    ) -> tuple[str | None, InlineKeyboardMarkup | None]:
        """Generate the rich HTML content and main action keyboard for a ticket session."""
        session = cls.get_session(token)
        if not session:
            return None, None
        rich_html = format_ticket_rich_html(session)
        keyboard = TicketKeyboardBuilder.build_main_ticket_keyboard(token)
        return rich_html, keyboard

    @classmethod
    def build_split_summary_message(
        cls, token: str
    ) -> tuple[
        str | None,
        InlineKeyboardMarkup | None,
        dict[str, dict[str, Any]] | None,
        str | None,
    ]:
        """Calculate and format the split summary for a ticket session."""
        session = cls.get_session(token)
        if not session:
            return None, None, None, None
        shares = session.calculate_split()
        summary_md = format_ticket_split_summary(session, shares)
        rich_html = format_ticket_split_rich_html(session, shares)
        keyboard = TicketKeyboardBuilder.build_split_confirmation_keyboard(token)
        return summary_md, keyboard, shares, rich_html

    @classmethod
    async def process_receipt_image(
        cls,
        bot: Bot,
        media_message: Message,
        chat_id: int | None = None,
    ) -> tuple[Receipt, str]:
        """Download, parse via Gemini, and return (Receipt, formatted_markdown)."""
        has_media = bool(
            getattr(media_message, "photo", None)
            or getattr(media_message, "document", None)
        )
        if not has_media:
            raise ValidationError("Message does not contain a photo or image document.")

        if chat_id is not None:
            with contextlib.suppress(Exception):
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        image_bytes, mime_type = await ReceiptImageDownloader.download(
            bot, media_message
        )
        parser = get_receipt_parser()
        receipt = await parser.parse(image_bytes, mime_type=mime_type)
        formatted_text = cls.format_receipt_breakdown(receipt)
        return receipt, formatted_text

    @classmethod
    def record_ticket_expense(
        cls,
        token: str,
        db_session: Session,
        payer_id: int,
        payer_username: str | None,
        payer_first_name: str | None,
        chat_id: int,
        chat_title: str | None = None,
    ) -> tuple[str, InlineKeyboardMarkup | None]:
        """Calculate shares from ticket session and execute /pay command via CommandDispatcher."""
        session = cls.get_session(token)
        if not session:
            raise ValidationError("Ticket session has expired or was not found.")

        split_shares = session.calculate_split()
        if not split_shares:
            raise ValidationError(
                "No participants have claimed any items on this ticket."
            )

        group_repo = GroupRepository(db_session)
        group = group_repo.get_by_telegram_id(chat_id)
        if not group:
            group = group_repo.create_group(chat_id=chat_id, title=chat_title)

        user_repo = UserRepository(db_session)

        # Total amount
        total_amount = sum(p["total_share"] for p in split_shares.values())
        desc = session.receipt.merchant or "Receipt"

        split_tokens = []
        for p in split_shares.values():
            uid = p.get("user_id")
            share_amt = p["total_share"]

            if uid == payer_id:
                split_tokens.append(f"me:{share_amt:.2f}")
            elif p.get("username"):
                uname = p["username"].lstrip("@")
                split_tokens.append(f"@{uname}:{share_amt:.2f}")
            else:
                clean_name = p["display_name"].strip()
                uname_slug = clean_name.lower().replace(" ", "_")
                ext_u = crud.get_user_in_group(db_session, group.id, uname_slug)
                if not ext_u:
                    user_repo.create_external(
                        group=group,
                        first_name=clean_name,
                        username=uname_slug,
                    )
                    db_session.flush()
                split_tokens.append(f"@{uname_slug}:{share_amt:.2f}")

        split_clause = " ".join(split_tokens)
        cmd_str = f"/pay {total_amount:.2f} for {desc} by me split {split_clause}"

        result_text, reply_markup = CommandDispatcher.execute(
            command_str=cmd_str,
            chat_id=chat_id,
            creator_id=payer_id,
            creator_username=payer_username,
            creator_first_name=payer_first_name,
            session=db_session,
            chat_title=chat_title,
        )
        cls.pop_session(token)
        return result_text, reply_markup
