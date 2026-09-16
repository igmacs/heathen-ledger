import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Set, Dict


@dataclass
class PendingVoiceCommand:
    """Represents an unconfirmed voice command awaiting user action."""

    token: str
    command: str
    creator_id: Optional[int]
    creator_username: Optional[str]
    creator_first_name: Optional[str]
    authorized_user_ids: Set[int]
    chat_id: int
    transcription: str
    created_at: float = field(default_factory=time.time)


class PendingVoiceCommandStore:
    """In-memory store for voice commands pending user confirmation."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._commands: Dict[str, PendingVoiceCommand] = {}

    def prune_expired(self) -> None:
        """Remove commands older than ttl_seconds."""
        now = time.time()
        expired = [
            t
            for t, p in self._commands.items()
            if now - p.created_at > self.ttl_seconds
        ]
        for t in expired:
            self._commands.pop(t, None)

    def store(
        self,
        command: str,
        creator_id: Optional[int],
        creator_username: Optional[str],
        creator_first_name: Optional[str],
        authorized_user_ids: Set[int],
        chat_id: int,
        transcription: str,
    ) -> str:
        """Store an unconfirmed voice command and return a short unique token."""
        self.prune_expired()
        token = uuid.uuid4().hex[:10]
        self._commands[token] = PendingVoiceCommand(
            token=token,
            command=command,
            creator_id=creator_id,
            creator_username=creator_username,
            creator_first_name=creator_first_name,
            authorized_user_ids=authorized_user_ids,
            chat_id=chat_id,
            transcription=transcription,
            created_at=time.time(),
        )
        return token

    def get(self, token: str) -> Optional[PendingVoiceCommand]:
        """Retrieve a pending voice command by token."""
        return self._commands.get(token)

    def pop(self, token: str) -> Optional[PendingVoiceCommand]:
        """Atomically pop a pending voice command by token."""
        return self._commands.pop(token, None)

    def clear(self) -> None:
        """Clear all pending commands (useful for test isolation)."""
        self._commands.clear()
