"""
Vera AI Challenge — In-Memory Context Store
Versioned, idempotent storage for category/merchant/customer/trigger contexts.
"""

from __future__ import annotations
import threading
from typing import Any, Optional


class ContextStore:
    """Thread-safe in-memory context store, keyed by (scope, context_id)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (scope, context_id) -> {"version": int, "payload": dict}
        self._store: dict[tuple[str, str], dict[str, Any]] = {}
        # Track last send timestamp per merchant for cooldown
        self._last_send_ts: dict[str, float] = {}
        # Suppression registry: suppression_key -> True
        self._suppressed: set[str] = set()
        # Ended conversations: conversation_id -> True
        self._ended_conversations: set[str] = set()

    # ── Core CRUD ────────────────────────────────────────────

    def upsert(self, scope: str, context_id: str, version: int, payload: dict) -> tuple[bool, int | None]:
        """
        Insert or update a context.
        Returns (accepted, current_version_if_rejected).
        Idempotent on (context_id, version). Higher version replaces atomically.
        """
        key = (scope, context_id)
        with self._lock:
            existing = self._store.get(key)
            if existing and existing["version"] >= version:
                # Same or older version = stale; reject idempotently
                return False, existing["version"]
            self._store[key] = {"version": version, "payload": payload}
            return True, None

    def get(self, scope: str, context_id: str) -> Optional[dict]:
        """Get the payload for a (scope, context_id). Returns None if missing."""
        entry = self._store.get((scope, context_id))
        return entry["payload"] if entry else None

    def get_version(self, scope: str, context_id: str) -> int:
        entry = self._store.get((scope, context_id))
        return entry["version"] if entry else 0

    # ── Lookups ──────────────────────────────────────────────

    def get_category(self, slug: str) -> Optional[dict]:
        return self.get("category", slug)

    def get_merchant(self, merchant_id: str) -> Optional[dict]:
        return self.get("merchant", merchant_id)

    def get_customer(self, customer_id: str) -> Optional[dict]:
        return self.get("customer", customer_id)

    def get_trigger(self, trigger_id: str) -> Optional[dict]:
        return self.get("trigger", trigger_id)

    def get_merchant_category(self, merchant: dict) -> Optional[dict]:
        """Given a merchant payload, find its CategoryContext."""
        slug = merchant.get("category_slug")
        return self.get_category(slug) if slug else None

    # ── Counts ───────────────────────────────────────────────

    def counts(self) -> dict[str, int]:
        """Return count of stored contexts per scope."""
        c = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
        for (scope, _) in self._store:
            if scope in c:
                c[scope] += 1
        return c

    # ── Suppression ──────────────────────────────────────────

    def is_suppressed(self, suppression_key: str) -> bool:
        return suppression_key in self._suppressed

    def suppress(self, suppression_key: str) -> None:
        with self._lock:
            self._suppressed.add(suppression_key)

    # ── Send tracking ────────────────────────────────────────

    def record_send(self, merchant_id: str, ts: float) -> None:
        with self._lock:
            self._last_send_ts[merchant_id] = ts

    def last_send_time(self, merchant_id: str) -> float:
        return self._last_send_ts.get(merchant_id, 0.0)

    # ── Conversation management ──────────────────────────────

    def end_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self._ended_conversations.add(conversation_id)

    def is_conversation_ended(self, conversation_id: str) -> bool:
        return conversation_id in self._ended_conversations
