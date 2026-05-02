"""
Vera AI Challenge — Reply Handler
Rule-first reply classification with LLM fallback.
Handles: stop, yes/intent, auto-reply, question, hostile, off-topic.
"""

from __future__ import annotations
from typing import Optional


# ── Intent detection constants ───────────────────────────────

_STOP_KEYWORDS = [
    "stop", "unsubscribe", "not interested", "don't message", "dont message",
    "spam", "leave me alone", "block", "remove me", "opt out", "opt-out",
    "band karo", "mat karo", "nahi chahiye", "stop messaging",
    "useless", "bothering", "harassing",
]

_YES_KEYWORDS = [
    "yes", "ok", "sure", "let's do it", "lets do it", "go ahead",
    "do it", "haan", "ha", "chalega", "kar do", "karo", "theek hai",
    "thik hai", "proceed", "confirm", "done", "send", "agreed",
    "sounds good", "let's go", "lets go", "okay", "start",
    "what's next", "whats next", "next step",
]

_AUTO_REPLY_PATTERNS = [
    "thank you for contacting",
    "our team will respond",
    "we will get back to you",
    "automated response",
    "automated assistant",
    "auto-reply",
    "thank you for your message",
    "currently unavailable",
    "will revert shortly",
    "aapki jaankari ke liye",
    "hamari team",
    "we are currently",
]


class ReplyHandler:
    """
    Stateful reply handler that tracks conversation state per conversation_id.
    Uses rule-first classification — LLM is only used as fallback for ambiguous messages.
    """

    def __init__(self) -> None:
        # conversation_id -> list of messages from merchant/customer
        self._history: dict[str, list[str]] = {}
        # conversation_id -> auto-reply count
        self._auto_reply_count: dict[str, int] = {}

    def classify(self, conversation_id: str, merchant_id: str, message: str, turn_number: int) -> dict:
        """
        Classify a merchant/customer reply and return the action.

        Returns dict with:
          action: "send" | "wait" | "end"
          body: str (if action == "send")
          cta: str (if action == "send")
          wait_seconds: int (if action == "wait")
          rationale: str
        """
        msg_lower = message.strip().lower()

        # Track history
        self._history.setdefault(conversation_id, []).append(message)

        # ── Rule 1: STOP / hostile / opt-out ─────────────────
        if self._is_stop(msg_lower):
            return {
                "action": "end",
                "rationale": "Merchant explicitly opted out or expressed frustration. Closing conversation gracefully.",
            }

        # ── Rule 2: Auto-reply detection ─────────────────────
        if self._is_auto_reply(msg_lower, conversation_id):
            # Track auto-replies by merchant_id to handle cross-thread detection
            track_id = merchant_id or conversation_id
            self._auto_reply_count.setdefault(track_id, 0)
            self._auto_reply_count[track_id] += 1
            count = self._auto_reply_count[track_id]

            if count >= 3:
                # 3rd+ auto-reply → end
                return {
                    "action": "end",
                    "rationale": f"Auto-reply detected {count}x in a row. No real engagement signal; closing conversation.",
                }
            elif count == 2:
                # 2nd auto-reply → wait 24h
                return {
                    "action": "wait",
                    "wait_seconds": 86400,
                    "rationale": f"Same auto-reply {count}x. Owner likely not at phone. Waiting 24h before retry.",
                }
            else:
                # 1st auto-reply → send one acknowledgment
                return {
                    "action": "send",
                    "body": "Looks like an auto-reply — no worries. When the owner sees this, just reply 'Yes' to continue.",
                    "cta": "binary_yes_no",
                    "rationale": "Detected auto-reply (canned response pattern). One prompt to flag for owner.",
                }
        else:
            # Reset auto-reply counter on real message (same key as tracking)
            track_id = merchant_id or conversation_id
            self._auto_reply_count[track_id] = 0

        # ── Rule 3: YES / Intent / Commitment ────────────────
        if self._is_yes_intent(msg_lower):
            return {
                "action": "send",
                "body": None,  # Will be filled by message_generator with action-mode content
                "cta": "open_ended",
                "intent": "confirm",
                "rationale": "Merchant committed. Switching to action mode — delivering the requested work.",
            }

        # ── Rule 4: Question ─────────────────────────────────
        if self._is_question(msg_lower, message):
            return {
                "action": "send",
                "body": None,  # Will be filled by message_generator
                "cta": "open_ended",
                "intent": "question",
                "rationale": "Merchant asked a question. Answering from available context.",
            }

        # ── Fallback: treat as general engagement ────────────
        return {
            "action": "send",
            "body": None,  # Will be filled by message_generator
            "cta": "open_ended",
            "intent": "general",
            "rationale": "Merchant replied with general engagement. Continuing conversation thread.",
        }

    def _is_stop(self, msg: str) -> bool:
        """Check if message indicates opt-out or hostility."""
        for kw in _STOP_KEYWORDS:
            if kw in msg:
                return True
        return False

    def _is_auto_reply(self, msg: str, conversation_id: str) -> bool:
        """
        Detect auto-replies:
        1. Pattern matching against known canned response phrases
        2. Identical message repeated (hash comparison)
        """
        # Pattern-based detection
        for pattern in _AUTO_REPLY_PATTERNS:
            if pattern in msg:
                return True

        # Repetition-based detection: same message as last one
        history = self._history.get(conversation_id, [])
        if len(history) >= 2:
            if history[-1].strip().lower() == history[-2].strip().lower():
                return True

        return False

    def _is_yes_intent(self, msg: str) -> bool:
        """Check if message signals positive intent / commitment."""
        for kw in _YES_KEYWORDS:
            if kw in msg:
                return True
        return False

    def _is_question(self, msg_lower: str, msg_original: str) -> bool:
        """Check if the message is a question."""
        if msg_original.strip().endswith("?"):
            return True
        question_words = ["what", "how", "when", "where", "why", "can you", "could you", "kya", "kaise", "kab"]
        for qw in question_words:
            if msg_lower.startswith(qw):
                return True
        return False

    def get_conversation_history(self, conversation_id: str) -> list[str]:
        """Return the message history for a conversation."""
        return self._history.get(conversation_id, [])
