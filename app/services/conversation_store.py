"""
Per-session conversation store for CONFIG chaining (CONFIG_INTENT_PLAN.md §5).

Phase 0 (MVP): in-process dict with TTL — formalises the existing unused
`chat_sessions` dict in models.py. Production swaps the backend (Redis/SQLite)
behind the same interface (§17). Per-process only; needs a shared backend before
running with workers > 1 (§15).
"""
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field

from ..models import ChatMessage, ConfigState
from .. import logger

# Session time-to-live. Stale sessions are dropped (clears any half-filled CONFIG).
SESSION_TTL = timedelta(hours=2)
# Number of recent turns fed into classify_intent / CONFIG LLM calls.
HISTORY_WINDOW = 8


class ConversationState(BaseModel):
    session_id: str
    history: list[ChatMessage] = Field(default_factory=list)
    config_state: Optional[ConfigState] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ConversationStore:
    def __init__(self, ttl: timedelta = SESSION_TTL):
        self._store: dict[str, ConversationState] = {}
        self._ttl = ttl

    def _expired(self, state: ConversationState) -> bool:
        return datetime.utcnow() - state.updated_at > self._ttl

    def load(self, session_id: str) -> ConversationState:
        state = self._store.get(session_id)
        if state is not None and self._expired(state):
            logger.info("Session %r expired (TTL); clearing state", session_id)
            self._store.pop(session_id, None)
            state = None
        if state is None:
            state = ConversationState(session_id=session_id)
            self._store[session_id] = state
        return state

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        state = self.load(session_id)
        state.history.append(ChatMessage(role=role, content=content))
        state.updated_at = datetime.utcnow()

    def recent(self, session_id: str, n: int = HISTORY_WINDOW) -> list[ChatMessage]:
        state = self.load(session_id)
        return state.history[-n:]

    def format_recent(self, session_id: str, n: int = HISTORY_WINDOW, max_chars: int = 500) -> str:
        """Recent turns as a 'role: content' transcript, each message truncated so a
        prior long turn (e.g. a rendered playbook) can't bloat downstream prompts."""
        lines = []
        for m in self.recent(session_id, n):
            content = m.content if len(m.content) <= max_chars else m.content[:max_chars] + " …[truncated]"
            lines.append(f"{m.role}: {content}")
        return "\n".join(lines)

    def get_config_state(self, session_id: str) -> Optional[ConfigState]:
        return self.load(session_id).config_state

    def set_config_state(self, session_id: str, config_state: ConfigState) -> None:
        state = self.load(session_id)
        state.config_state = config_state
        state.updated_at = datetime.utcnow()

    def clear_config_state(self, session_id: str) -> None:
        state = self.load(session_id)
        state.config_state = None
        state.updated_at = datetime.utcnow()


# Module-level singleton (per process).
conversation_store = ConversationStore()
