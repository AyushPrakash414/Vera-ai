"""
Vera AI Challenge — Trigger Dispatcher
Orchestrates the full tick cycle: filter → rank → compose → validate → return actions.
"""

from __future__ import annotations
import time, uuid, logging
from typing import Optional

from app.context_store import ContextStore
from app.decision_engine import should_send, score_trigger
from app.fact_extractor import extract_facts
from app.cta_engine import decide_cta, decide_send_as
from app.message_generator import generate_message_body
from app.validator import validate_message, build_rationale
from app.config import MAX_ACTIONS_PER_TICK

logger = logging.getLogger(__name__)


def dispatch_tick(
    store: ContextStore,
    available_trigger_ids: list[str],
    now_iso: str,
) -> list[dict]:
    """
    Process a tick: evaluate all available triggers, decide which to act on,
    generate messages, validate, and return actions.
    """
    now_ts = time.time()
    candidates: list[tuple[float, str, dict]] = []  # (score, trigger_id, trigger_payload)

    # ── Step 1: Score & filter all triggers ──────────────────
    for tid in available_trigger_ids:
        trigger = store.get_trigger(tid)
        if not trigger:
            continue

        merchant_id = trigger.get("merchant_id")
        if not merchant_id:
            continue

        merchant = store.get_merchant(merchant_id)
        if not merchant:
            continue

        # Get optional customer
        customer_id = trigger.get("customer_id")
        customer = store.get_customer(customer_id) if customer_id else None

        # Decision: should we send?
        can_send, reason = should_send(trigger, merchant, store, customer, now_ts)
        if not can_send:
            logger.info(f"Skipping {tid}: {reason}")
            continue

        # Score the trigger
        s = score_trigger(trigger, merchant, store, now_ts)
        candidates.append((s, tid, trigger))

    if not candidates:
        return []

    # ── Step 2: Sort by score descending, take top N ─────────
    candidates.sort(key=lambda x: x[0], reverse=True)
    selected = candidates[:MAX_ACTIONS_PER_TICK]

    # ── Step 3: Compose messages for selected triggers ───────
    actions = []
    processed_merchants: set[str] = set()

    for score_val, tid, trigger in selected:
        merchant_id = trigger.get("merchant_id", "")

        # One action per merchant per tick
        if merchant_id in processed_merchants:
            continue

        merchant = store.get_merchant(merchant_id)
        if not merchant:
            continue

        category = store.get_merchant_category(merchant)
        if not category:
            continue

        customer_id = trigger.get("customer_id")
        customer = store.get_customer(customer_id) if customer_id else None

        trigger_kind = trigger.get("kind", "unknown")
        trigger_scope = trigger.get("scope", "merchant")
        suppression_key = trigger.get("suppression_key", "")

        # Rule-based decisions
        cta_type = decide_cta(trigger_kind, trigger_scope)
        send_as = decide_send_as(trigger_scope, customer)

        # Extract facts
        facts = extract_facts(category, merchant, trigger, customer)

        # Generate message body deterministically
        try:
            body = generate_message_body(
                facts=facts,
                category=category,
                trigger_kind=trigger_kind,
                cta_type=cta_type,
                send_as=send_as,
                customer=customer,
            )
        except Exception as e:
            logger.error(f"Generation failed for {tid}: {e}")
            continue

        # Validate
        is_valid, issues = validate_message(body, facts, category)
        if not is_valid:
            logger.warning(f"Validation issues for {tid}: {issues}")
            # Still send if body exists — issues are warnings not blockers
            if not body:
                continue

        # Build rationale
        rationale = build_rationale(facts, f"Score={score_val:.1f}; sent because trigger matched merchant state")

        # Build conversation_id
        conv_id = f"conv_{merchant_id}_{trigger_kind}_{tid.split('_')[1] if '_' in tid else 'x'}"

        # Build template params
        owner = facts.get("owner_first_name", "")
        merchant_name = facts.get("merchant_name", "")
        template_params = [owner or merchant_name, trigger_kind, body[:80]]

        action = {
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": send_as,
            "trigger_id": tid,
            "template_name": f"vera_{trigger_kind}_v1",
            "template_params": template_params,
            "body": body,
            "cta": cta_type,
            "suppression_key": suppression_key,
            "rationale": rationale,
        }

        actions.append(action)
        processed_merchants.add(merchant_id)

        # Record send + suppress
        store.record_send(merchant_id, now_ts)
        if suppression_key:
            store.suppress(suppression_key)

    return actions
