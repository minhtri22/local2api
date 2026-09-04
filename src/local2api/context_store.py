from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from local2api.config import Settings


@dataclass(frozen=True)
class ConversationMetadata:
    """Metadata for a conversation."""
    conversation_id: str
    created_at: float
    updated_at: float
    turn_count: int
    title: Optional[str] = None


@dataclass
class CanonicalContext:
    """Gateway-owned canonical conversation state.

    This is the single source of truth for conversation/task context,
    independent of any backend session.
    """
    conversation_id: str
    turn_id: str
    system_instructions: list[str] = field(default_factory=list)
    task_goal: str = ""
    hard_constraints: list[str] = field(default_factory=list)
    known_facts: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    recent_turns: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    backend_history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalContext":
        return cls(**data)

    @property
    def turn_count(self) -> int:
        return len(self.recent_turns)


class ContextStore:
    """SQLite-backed persistent context store.

    Provides durable storage for canonical conversation state.
    Thread-safe for concurrent access.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        conversation_id TEXT PRIMARY KEY,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        turn_count INTEGER NOT NULL DEFAULT 0,
                        title TEXT,
                        context_json TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conversations_updated
                    ON conversations(updated_at)
                """)
                conn.commit()

    def create_conversation(
        self,
        conversation_id: Optional[str] = None,
        system_instructions: Optional[list[str]] = None,
        task_goal: str = "",
        hard_constraints: Optional[list[str]] = None,
        decisions: Optional[list[dict[str, Any]]] = None,
        artifacts: Optional[list[dict[str, Any]]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> CanonicalContext:
        """Create a new conversation with initial state."""
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        now = time.time()
        context = CanonicalContext(
            conversation_id=conversation_id,
            turn_id=str(uuid.uuid4()),
            system_instructions=system_instructions or [],
            task_goal=task_goal,
            hard_constraints=hard_constraints or [],
            decisions=decisions or [],
            artifacts=artifacts or [],
            metadata=metadata or {"created_at": now},
        )
        self._save_context(context, turn_count=0, title=None)
        return context

    def get_conversation(self, conversation_id: str) -> Optional[CanonicalContext]:
        """Load canonical context for a conversation."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT context_json FROM conversations WHERE conversation_id = ?",
                    (conversation_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                data = json.loads(row["context_json"])
                return CanonicalContext.from_dict(data)

    def update_conversation(
        self,
        context: CanonicalContext,
        turn_count: int,
        title: Optional[str] = None,
    ) -> None:
        """Save updated canonical context."""
        self._save_context(context, turn_count, title)

    def _save_context(
        self,
        context: CanonicalContext,
        turn_count: int,
        title: Optional[str],
    ) -> None:
        """Persist canonical context to SQLite."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO conversations
                    (conversation_id, created_at, updated_at, turn_count, title, context_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        context.conversation_id,
                        context.metadata.get("created_at", time.time()),
                        time.time(),
                        turn_count,
                        title,
                        json.dumps(context.to_dict()),
                    ),
                )
                conn.commit()

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation. Returns True if deleted."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM conversations WHERE conversation_id = ?",
                    (conversation_id,),
                )
                conn.commit()
                return cursor.rowcount > 0

    def list_conversations(self, limit: int = 100) -> list[ConversationMetadata]:
        """List recent conversations."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    """
                    SELECT conversation_id, created_at, updated_at, turn_count, title
                    FROM conversations
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
                return [
                    ConversationMetadata(
                        conversation_id=row["conversation_id"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        turn_count=row["turn_count"],
                        title=row["title"],
                    )
                    for row in cursor.fetchall()
                ]

    def clear_all(self) -> int:
        """Delete all conversations. Returns count deleted."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("DELETE FROM conversations")
                conn.commit()
                return cursor.rowcount


def get_context_store(settings: Settings) -> ContextStore:
    """Factory function to create ContextStore from settings."""
    db_path = os.getenv("LOCAL2API_CONTEXT_DB", settings.context_db_path if hasattr(settings, "context_db_path") else "data/context.db")
    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return ContextStore(db_path)


# For testing - in-memory store
def get_test_context_store() -> ContextStore:
    """Create an in-memory context store for testing."""
    return ContextStore(":memory:")