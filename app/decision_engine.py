"""
Vera AI Challenge — Decision Engine
Determines whether to SEND, WAIT, or SUPPRESS for a given trigger.
Purely rule-based. No LLM calls.
"""

from __future__ import annotations
import time
from typing import Optional

from app.context_store import ContextStore
from app.config import MERCHANT_COOLDOWN_SECONDS


def should_send(
    trigger: dict,
    merchant: dict,
    store: ContextStore,
    customer: Optional[dict] = None,
    now_ts: float | None = None,
) -> tuple[bool, str]:
    """
    Returns (should_send: bool, reason: str).
    If False, the trigger is skipped and reason explains why.
    """
    if now_ts is None:
        now_ts = time.time()

    merchant_id = trigger.get("merchant_id", "")
    suppression_key = trigger.get("suppression_key", "")
    trigger_kind = trigger.get("kind", "")
    urgency = trigger.get("urgency", 1)

    # 1. Check suppression registry
    if suppression_key and store.is_suppressed(suppression_key):
        return False, f"Suppressed: {suppression_key} already sent"

    # 2. Check consent for customer-scoped triggers
    if customer:
        consent_scope = customer.get("consent", {}).get("scope", [])
        opted_in_at = customer.get("consent", {}).get("opted_in_at")
        reminder_opt_in = customer.get("preferences", {}).get("reminder_opt_in", False)

        # No consent at all -> don't send
        if not opted_in_at and not reminder_opt_in:
            return False, "Customer has no consent for outreach"

        # Check if phone is recorded (walk-in anonymous customers)
        phone = customer.get("identity", {}).get("phone_redacted")
        if phone is None:
            return False, "Customer has no phone recorded"

        channel = customer.get("preferences", {}).get("channel", "")
        if channel == "none_recorded":
            return False, "Customer has no communication channel"

    # 3. Check merchant subscription status
    sub_status = merchant.get("subscription", {}).get("status", "")
    # Allow winback triggers for expired merchants
    if sub_status == "expired" and trigger_kind not in ("winback_eligible", "renewal_due", "dormant_with_vera"):
        return False, f"Merchant subscription expired, trigger '{trigger_kind}' not applicable"

    # 4. Check merchant cooldown (skip for high urgency >= 4)
    if urgency < 4:
        last_send = store.last_send_time(merchant_id)
        if last_send > 0 and (now_ts - last_send) < MERCHANT_COOLDOWN_SECONDS:
            return False, f"Merchant cooldown active: last send {int(now_ts - last_send)}s ago"

    # 5. Low-priority triggers get extra filtering
    if urgency <= 1:
        # If merchant is dormant for 30+ days AND trigger is just a curiosity ask, still send
        # But if we recently sent anything, skip
        last_send = store.last_send_time(merchant_id)
        if last_send > 0 and (now_ts - last_send) < MERCHANT_COOLDOWN_SECONDS * 2:
            return False, f"Low-priority trigger skipped: recent activity within {MERCHANT_COOLDOWN_SECONDS * 2}s"

    return True, "All checks passed"


def score_trigger(trigger: dict, merchant: dict, store: ContextStore, now_ts: float | None = None) -> float:
    """
    Score a trigger for prioritization.
    Higher score = process first.
    Formula: urgency_weight + merchant_signal_weight + recency_penalty + suppression_penalty
    """
    if now_ts is None:
        now_ts = time.time()

    urgency = trigger.get("urgency", 1)
    merchant_id = trigger.get("merchant_id", "")
    suppression_key = trigger.get("suppression_key", "")
    kind = trigger.get("kind", "")

    # Base: urgency * 10
    score = urgency * 10.0

    # Merchant signal bonus: active signals that match the trigger
    signals = merchant.get("signals", [])
    signal_bonus = 0.0
    if kind == "perf_dip" and any("perf_dip" in s for s in signals):
        signal_bonus += 5.0
    if kind == "winback_eligible" and "winback_eligible" in signals:
        signal_bonus += 5.0
    if kind == "renewal_due" and any("renewal" in s for s in signals):
        signal_bonus += 5.0
    if kind == "perf_spike" and any("growing" in s for s in signals):
        signal_bonus += 3.0
    # Customer-scoped triggers get a priority boost (differentiation)
    if trigger.get("scope") == "customer":
        signal_bonus += 8.0

    score += signal_bonus

    # Recency penalty: reduce score if we sent to this merchant recently
    last_send = store.last_send_time(merchant_id)
    if last_send > 0:
        hours_since = (now_ts - last_send) / 3600
        if hours_since < 1:
            score -= 15.0
        elif hours_since < 6:
            score -= 5.0

    # Suppression penalty: already suppressed means -100
    if suppression_key and store.is_suppressed(suppression_key):
        score -= 100.0

    return score
