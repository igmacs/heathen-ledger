import time
import uuid
from typing import Dict, Any, Optional
from telegram import InlineKeyboardMarkup


class EphemeralPayloadStore:
    """In-memory cache for storing ephemeral messages that can be persisted to groups."""

    def __init__(self, payloads: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self.payloads: Dict[str, Dict[str, Any]] = (
            payloads if payloads is not None else {}
        )

    def prune_expired(self, max_age_seconds: int = 3600) -> None:
        """Remove stored persist payloads older than max_age_seconds or truncate if too large."""
        now = time.time()
        expired = [
            k
            for k, v in self.payloads.items()
            if now - v.get("created_at", 0) > max_age_seconds
        ]
        for k in expired:
            self.payloads.pop(k, None)
        if len(self.payloads) > 1000:
            sorted_keys = sorted(
                self.payloads.keys(),
                key=lambda k: self.payloads[k].get("created_at", 0),
            )
            for k in sorted_keys[: len(self.payloads) - 500]:
                self.payloads.pop(k, None)

    def store(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        parse_mode: Optional[str],
        reply_markup: Optional[InlineKeyboardMarkup],
    ) -> str:
        """Store a new persist payload and return a unique token."""
        self.prune_expired()
        token = uuid.uuid4().hex[:12]
        self.payloads[token] = {
            "chat_id": chat_id,
            "user_id": user_id,
            "text": text,
            "parse_mode": parse_mode,
            "reply_markup": reply_markup,
            "created_at": time.time(),
        }
        return token

    def get(self, token: str) -> Optional[Dict[str, Any]]:
        """Retrieve payload by token without removing."""
        return self.payloads.get(token)

    def pop(self, token: str) -> Optional[Dict[str, Any]]:
        """Atomically pop payload by token."""
        return self.payloads.pop(token, None)

    def restore(self, token: str, payload: Dict[str, Any]) -> None:
        """Put back a payload."""
        self.payloads[token] = payload
