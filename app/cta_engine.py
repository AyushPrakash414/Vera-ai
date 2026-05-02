"""
Vera AI Challenge — CTA Engine
Purely rule-based CTA selection. The LLM NEVER decides the CTA.
"""

from __future__ import annotations


# ── CTA type constants ───────────────────────────────────────
CTA_BINARY_YES_NO = "binary_yes_no"
CTA_OPEN_ENDED = "open_ended"
CTA_MULTI_CHOICE = "multi_choice_slot"
CTA_BINARY_CONFIRM = "binary_confirm_cancel"
CTA_NONE = "none"


# ── Rule map: trigger_kind -> CTA type ───────────────────────
_CTA_RULES: dict[str, str] = {
    # High urgency — binary CTAs to drive immediate action
    "perf_spike": CTA_OPEN_ENDED,
    "perf_dip": CTA_BINARY_YES_NO,
    "seasonal_perf_dip": CTA_BINARY_YES_NO,
    "supply_alert": CTA_BINARY_YES_NO,
    "regulation_change": CTA_OPEN_ENDED,
    "active_planning_intent": CTA_OPEN_ENDED,
    "renewal_due": CTA_BINARY_YES_NO,

    # Medium urgency — engagement-oriented
    "research_digest": CTA_OPEN_ENDED,
    "recall_due": CTA_MULTI_CHOICE,
    "chronic_refill_due": CTA_BINARY_CONFIRM,
    "customer_lapsed_hard": CTA_BINARY_YES_NO,
    "customer_lapsed_soft": CTA_BINARY_YES_NO,
    "winback_eligible": CTA_BINARY_YES_NO,
    "competitor_opened": CTA_OPEN_ENDED,
    "wedding_package_followup": CTA_BINARY_YES_NO,
    "trial_followup": CTA_BINARY_YES_NO,

    # Low urgency — curiosity / informational
    "milestone_reached": CTA_OPEN_ENDED,
    "festival_upcoming": CTA_OPEN_ENDED,
    "ipl_match_today": CTA_BINARY_YES_NO,
    "review_theme_emerged": CTA_OPEN_ENDED,
    "curious_ask_due": CTA_OPEN_ENDED,
    "category_seasonal": CTA_OPEN_ENDED,
    "dormant_with_vera": CTA_OPEN_ENDED,
    "gbp_unverified": CTA_BINARY_YES_NO,
    "cde_opportunity": CTA_BINARY_YES_NO,
    "category_trend_movement": CTA_OPEN_ENDED,
}


def decide_cta(trigger_kind: str, trigger_scope: str = "merchant") -> str:
    """
    Determine the CTA type based purely on the trigger kind.
    Returns one of the CTA_* constants.
    """
    return _CTA_RULES.get(trigger_kind, CTA_OPEN_ENDED)


def decide_send_as(trigger_scope: str, customer: dict | None) -> str:
    """
    Determine send_as based on whether this is a customer-scoped message.
    Rule: if customer context is present AND trigger scope is 'customer', send as merchant.
    Otherwise send as vera.
    """
    if customer and trigger_scope == "customer":
        return "merchant_on_behalf"
    return "vera"
