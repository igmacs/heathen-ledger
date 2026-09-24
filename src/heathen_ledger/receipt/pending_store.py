"""In-memory store and session model for interactive ticket claiming and splitting."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .base import Receipt


def extract_initials(
    first_name: str,
    last_name: str | None = None,
    username: str | None = None,
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
    user_id: int | None = None
    username: str | None = None
    is_external: bool = False


@dataclass
class TicketItemState:
    """Represents the interactive state of a single ticket entry."""

    item_index: int
    name: str
    price: float
    participants: dict[str, TicketParticipant] = field(default_factory=dict)
    is_completed: bool = False

    @property
    def initials_list(self) -> list[str]:
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
    creator_id: int | None
    creator_name: str | None
    receipt: Receipt
    items: list[TicketItemState] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    message_id: int | None = None
    ephemeral_message_id: int | None = None
    external_participants: dict[str, TicketParticipant] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        chat_id: int,
        creator_id: int | None,
        creator_name: str | None,
        receipt: Receipt,
        token: str | None = None,
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

    def register_external_participant(self, name: str) -> TicketParticipant:
        """Register or retrieve an external participant by display name."""
        clean_name = name.strip()
        slug = clean_name.lower().replace(" ", "_")[:16]
        key = f"ext:{slug}"
        if key in self.external_participants:
            return self.external_participants[key]
        initials = extract_initials(clean_name)
        p = TicketParticipant(
            participant_key=key,
            display_name=clean_name,
            initials=initials,
            user_id=None,
            username=None,
            is_external=True,
        )
        self.external_participants[key] = p
        return p

    def get_known_external_participants(self) -> list[TicketParticipant]:
        """Return list of all external participants registered in this session."""
        known = dict(self.external_participants)
        for it in self.items:
            for k, p in it.participants.items():
                if p.is_external and k not in known:
                    known[k] = p
        return list(known.values())

    def toggle_participant(
        self,
        item_index: int,
        user_id: int | None,
        display_name: str,
        username: str | None = None,
        last_name: str | None = None,
    ) -> bool:
        """Toggle user participation in an item. Returns True if added, False if removed."""
        if item_index < 0 or item_index >= len(self.items):
            return False

        item = self.items[item_index]
        if user_id is not None:
            key = f"tg:{user_id}"
            is_ext = False
        else:
            clean_name = display_name.strip()
            slug = clean_name.lower().replace(" ", "_")[:16]
            key = f"ext:{slug}"
            is_ext = True

        if key in item.participants:
            del item.participants[key]
            return False
        else:
            initials = extract_initials(display_name, last_name, username)
            p = TicketParticipant(
                participant_key=key,
                display_name=display_name,
                initials=initials,
                user_id=user_id,
                username=username,
                is_external=is_ext,
            )
            item.participants[key] = p
            if is_ext:
                self.external_participants[key] = p
            return True

    def toggle_participant_by_key(
        self,
        item_index: int,
        participant_key: str,
        participant: TicketParticipant | None = None,
    ) -> bool:
        """Toggle a participant on an item by key. Returns True if added, False if removed."""
        if item_index < 0 or item_index >= len(self.items):
            return False

        item = self.items[item_index]
        if participant_key in item.participants:
            del item.participants[participant_key]
            return False

        if participant is None:
            participant = self.external_participants.get(participant_key)
            if not participant:
                for it in self.items:
                    if participant_key in it.participants:
                        participant = it.participants[participant_key]
                        break

        if participant:
            item.participants[participant_key] = participant
            if participant.is_external:
                self.external_participants[participant_key] = participant
            return True
        return False

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
        p = self.register_external_participant(name)
        item.participants[p.participant_key] = p
        return True

    def calculate_split(self) -> dict[str, dict[str, Any]]:
        """Calculate each participant's share of item costs plus proportional tax/tip/rounding.

        Returns a dictionary keyed by participant_key.
        """
        shares: dict[str, dict[str, Any]] = {}
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
        self._sessions: dict[str, PendingTicketSession] = {}

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

    def get(self, token: str) -> PendingTicketSession | None:
        """Retrieve a session by token."""
        return self._sessions.get(token)

    def pop(self, token: str) -> PendingTicketSession | None:
        """Remove and return a session by token."""
        return self._sessions.pop(token, None)

    def clear(self) -> None:
        """Clear all sessions (for testing)."""
        self._sessions.clear()
