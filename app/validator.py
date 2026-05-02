"""
Vera AI Challenge — Output Validator
Post-generation checks to ensure the LLM output meets all constraints.
Single validation pass — NO retries.
"""

from __future__ import annotations
from typing import Optional


def validate_message(
    body: str,
    facts: dict,
    category: dict,
) -> tuple[bool, list[str]]:
    """
    Validate a generated message body.
    Returns (is_valid, list_of_issues).
    """
    issues: list[str] = []

    # 1. Non-empty body
    if not body or not body.strip():
        issues.append("Empty message body")
        return False, issues

    # 2. Check for taboo words
    taboos = category.get("voice", {}).get("vocab_taboo", [])
    body_lower = body.lower()
    for taboo in taboos:
        # Handle compound taboos like "FDA-approved (use only when actually applicable)"
        check_word = taboo.split("(")[0].strip().lower()
        if check_word and check_word in body_lower:
            issues.append(f"Taboo word detected: '{check_word}'")

    # 3. Check for URLs (penalized -3 per URL by judge)
    if "http://" in body or "https://" in body or "www." in body:
        issues.append("URL detected in message body (penalized by judge)")

    # 4. Check for excessive length (WhatsApp readability)
    if len(body) > 1000:
        issues.append(f"Message too long: {len(body)} chars (aim for <500)")

    # 5. Check message doesn't contain raw JSON or technical artifacts
    if '{"' in body or "```" in body:
        issues.append("Raw JSON or code block detected in message body")

    is_valid = len(issues) == 0
    return is_valid, issues


def build_rationale(facts: dict, decision_reason: str = "") -> str:
    """
    Build a structured rationale string from facts.
    Format:
      Trigger: <kind>
      Merchant signal: <relevant signals>
      Decision: <action taken and why>
    """
    trigger_kind = facts.get("trigger_kind", "unknown")
    merchant_name = facts.get("merchant_name", "unknown")
    signals = facts.get("signals", [])
    top_offer = facts.get("top_offer", "none")
    trigger_scope = facts.get("trigger_scope", "merchant")

    # Pick the 2 most relevant signals
    relevant_signals = signals[:3] if signals else ["no_active_signals"]

    scope_label = "merchant-facing" if trigger_scope == "merchant" else "customer-facing"

    parts = [
        f"Trigger: {trigger_kind} ({scope_label})",
        f"Merchant: {merchant_name}",
    ]

    if relevant_signals:
        parts.append(f"Signals: {', '.join(relevant_signals)}")

    if top_offer:
        parts.append(f"Active offer: {top_offer}")

    if decision_reason:
        parts.append(f"Decision: {decision_reason}")

    # Add customer-specific info if present
    customer_name = facts.get("customer_name")
    if customer_name:
        customer_state = facts.get("customer_state", "unknown")
        parts.append(f"Customer: {customer_name} ({customer_state})")

    return "; ".join(parts)
