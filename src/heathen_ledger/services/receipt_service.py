"""Service layer for receipt photo parsing, interactive claiming, and itemization."""

import logging
from typing import Optional, Tuple, Dict, Any
from telegram import Bot, Message, InlineKeyboardMarkup
from telegram.constants import ChatAction
from sqlalchemy.orm import Session

from ..receipt import (
    Receipt,
    ReceiptImageDownloader,
    get_receipt_parser,
    PendingTicketSession,
    PendingTicketStore,
)
from ..receipt.formatter import (
    format_price,
    format_ticket_rich_html,
    format_ticket_split_rich_html,
    format_ticket_split_summary,
)
from ..keyboards.ticket import TicketKeyboardBuilder
from ..repositories import GroupRepository, UserRepository
from ..commands import CommandDispatcher
from .. import crud
from .exceptions import ValidationError

logger = logging.getLogger(__name__)


class ReceiptService:
    """Service orchestrating receipt image downloading, OCR parsing, and interactive splitting."""

    _store = PendingTicketStore()

    @classmethod
    def get_store(cls) -> PendingTicketStore:
        """Return the backing PendingTicketStore."""
        return cls._store

    @classmethod
    def format_price(cls, amount: float, currency: Optional[str] = None) -> str:
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
        creator_id: Optional[int],
        creator_name: Optional[str],
        receipt: Receipt,
        token: Optional[str] = None,
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
    def get_session(cls, token: str) -> Optional[PendingTicketSession]:
        """Retrieve an active ticket session by token."""
        return cls._store.get(token)

    @classmethod
    def pop_session(cls, token: str) -> Optional[PendingTicketSession]:
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
        username: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Tuple[Optional[PendingTicketSession], bool]:
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
    ) -> Tuple[Optional[PendingTicketSession], bool]:
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
        username: Optional[str] = None,
    ) -> Optional[PendingTicketSession]:
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
    ) -> Optional[PendingTicketSession]:
        """Assign an external non-group participant to an item."""
        session = cls.get_session(token)
        if not session:
            return None
        session.assign_external_participant(item_idx, name)
        return session

    @classmethod
    def build_ticket_rich_message(
        cls, token: str
    ) -> Tuple[Optional[str], Optional[InlineKeyboardMarkup]]:
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
    ) -> Tuple[
        Optional[str],
        Optional[InlineKeyboardMarkup],
        Optional[Dict[str, Dict[str, Any]]],
        Optional[str],
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
        chat_id: Optional[int] = None,
    ) -> Tuple[Receipt, str]:
        """Download, parse via Gemini, and return (Receipt, formatted_markdown)."""
        has_media = bool(
            getattr(media_message, "photo", None)
            or getattr(media_message, "document", None)
        )
        if not has_media:
            raise ValidationError("Message does not contain a photo or image document.")

        if chat_id is not None:
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass

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
        payer_username: Optional[str],
        payer_first_name: Optional[str],
        chat_id: int,
        chat_title: Optional[str] = None,
    ) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
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
