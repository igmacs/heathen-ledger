"""In-memory store and session model for interactive ticket claiming and splitting."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .base import Receipt


def extract_initials(
    first_name: str,
    last_name: Optional[str] = None,
    username: Optional[str] = None,
) -> str:
    """Derive clean 2-letter uppercase initials for visual feedback."""
    if first_name and last_name:
        return f"{first_name[0]}{last_name[0]}".upper()
    if first_name:
        parts = first_name.strip().split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[1][0]}".upper()
        if len(first_name) >= 2:
            return first_name[:2].upper()
        return first_name[0].upper()
    if username:
        clean = username.lstrip("@")
        return clean[:2].upper() if len(clean) >= 2 else clean.upper()
    return "??"


@dataclass
class TicketParticipant:
    """Represents a member registered on a ticket item."""

    participant_key: str  # "tg:<user_id>" or "ext:<name_slug>"
    display_name: str
    initials: str
    user_id: Optional[int] = None
    username: Optional[str] = None
    is_external: bool = False


@dataclass
class TicketItemState:
    """Represents the interactive state of a single ticket entry."""

    item_index: int
    name: str
    price: float
    participants: Dict[str, TicketParticipant] = field(default_factory=dict)
    is_completed: bool = False

    @property
    def initials_list(self) -> List[str]:
        return [p.initials for p in self.participants.values()]

    @property
    def initials_display(self) -> str:
        if not self.participants:
            return ""
        inits = ", ".join(self.initials_list)
        icon = "👤" if len(self.participants) == 1 else "👥"
        return f"{icon} {inits}"


@dataclass
class PendingTicketSession:
    """Manages the full lifecycle of an interactive ticket splitting session."""

    token: str
    chat_id: int
    creator_id: Optional[int]
    creator_name: Optional[str]
    receipt: Receipt
    items: List[TicketItemState] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    message_id: Optional[int] = None
    ephemeral_message_id: Optional[int] = None

    @classmethod
    def create(
        cls,
        chat_id: int,
        creator_id: Optional[int],
        creator_name: Optional[str],
        receipt: Receipt,
        token: Optional[str] = None,
    ) -> "PendingTicketSession":
        """Create a new ticket session with repeated items expanded into individual lines."""
        token = token or uuid.uuid4().hex[:8]
        expanded_items = receipt.expand_items()
        item_states = [
            TicketItemState(
                item_index=i,
                name=it.name,
                price=it.price,
            )
            for i, it in enumerate(expanded_items)
        ]
        return cls(
            token=token,
            chat_id=chat_id,
            creator_id=creator_id,
            creator_name=creator_name,
            receipt=receipt,
            items=item_states,
        )

    def toggle_participant(
        self,
        item_index: int,
        user_id: Optional[int],
        display_name: str,
        username: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> bool:
        """Toggle user participation in an item. Returns True if added, False if removed."""
        if item_index < 0 or item_index >= len(self.items):
            return False

        item = self.items[item_index]
        if user_id is not None:
            key = f"tg:{user_id}"
            is_ext = False
        else:
            key = f"ext:{display_name.lower().strip()}"
            is_ext = True

        if key in item.participants:
            del item.participants[key]
            return False
        else:
            initials = extract_initials(display_name, last_name, username)
            item.participants[key] = TicketParticipant(
                participant_key=key,
                display_name=display_name,
                initials=initials,
                user_id=user_id,
                username=username,
                is_external=is_ext,
            )
            return True

    def toggle_completed(self, item_index: int) -> bool:
        """Toggle completion/lock status of an item."""
        if item_index < 0 or item_index >= len(self.items):
            return False
        self.items[item_index].is_completed = not self.items[item_index].is_completed
        return self.items[item_index].is_completed

    def assign_external_participant(
        self,
        item_index: int,
        name: str,
    ) -> bool:
        """Assign an external user by name to an item."""
        if item_index < 0 or item_index >= len(self.items):
            return False
        item = self.items[item_index]
        clean_name = name.strip()
        key = f"ext:{clean_name.lower()}"
        initials = extract_initials(clean_name)
        item.participants[key] = TicketParticipant(
            participant_key=key,
            display_name=clean_name,
            initials=initials,
            user_id=None,
            username=None,
            is_external=True,
        )
        return True

    def calculate_split(self) -> Dict[str, Dict[str, Any]]:
        """Calculate each participant's share of item costs plus proportional tax/tip/rounding.

        Returns a dictionary keyed by participant_key.
        """
        shares: Dict[str, Dict[str, Any]] = {}
        items_allocated_total = 0.0

        for it in self.items:
            if not it.participants:
                continue
            split_price = round(it.price / len(it.participants), 2)
            item_allocated = split_price * (len(it.participants) - 1)
            last_split = round(it.price - item_allocated, 2)

            for idx, p in enumerate(it.participants.values()):
                amt = last_split if idx == len(it.participants) - 1 else split_price
                items_allocated_total = round(items_allocated_total + amt, 2)
                if p.participant_key not in shares:
                    shares[p.participant_key] = {
                        "display_name": p.display_name,
                        "username": p.username,
                        "user_id": p.user_id,
                        "initials": p.initials,
                        "is_external": p.is_external,
                        "items_subtotal": 0.0,
                        "extra_fee_share": 0.0,
                        "total_share": 0.0,
                    }
                shares[p.participant_key]["items_subtotal"] = round(
                    shares[p.participant_key]["items_subtotal"] + amt, 2
                )

        target_total = (
            self.receipt.total
            if self.receipt.total is not None
            else round(sum(it.price for it in self.items), 2)
        )
        extra_fees = round(target_total - items_allocated_total, 2)

        if shares and items_allocated_total > 0 and extra_fees != 0.0:
            allocated_extra = 0.0
            participants_list = list(shares.keys())
            for idx, key in enumerate(participants_list):
                if idx == len(participants_list) - 1:
                    person_extra = round(extra_fees - allocated_extra, 2)
                else:
                    ratio = shares[key]["items_subtotal"] / items_allocated_total
                    person_extra = round(extra_fees * ratio, 2)
                    allocated_extra = round(allocated_extra + person_extra, 2)

                shares[key]["extra_fee_share"] = person_extra

        for key in shares:
            shares[key]["total_share"] = round(
                shares[key]["items_subtotal"] + shares[key]["extra_fee_share"], 2
            )

        return shares


class PendingTicketStore:
    """In-memory store for active ticket splitting sessions."""

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: Dict[str, PendingTicketSession] = {}

    def prune_expired(self) -> None:
        """Remove expired sessions."""
        now = time.time()
        expired = [
            t
            for t, s in self._sessions.items()
            if now - s.created_at > self.ttl_seconds
        ]
        for t in expired:
            self._sessions.pop(t, None)

    def store(self, session: PendingTicketSession) -> str:
        """Store a session and return its token."""
        self.prune_expired()
        self._sessions[session.token] = session
        return session.token

    def get(self, token: str) -> Optional[PendingTicketSession]:
        """Retrieve a session by token."""
        return self._sessions.get(token)

    def pop(self, token: str) -> Optional[PendingTicketSession]:
        """Remove and return a session by token."""
        return self._sessions.pop(token, None)

    def clear(self) -> None:
        """Clear all sessions (for testing)."""
        self._sessions.clear()
