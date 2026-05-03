"""
Vera AI Challenge — Fact Extractor
Extracts clean, structured facts from raw contexts BEFORE passing to the LLM.
The LLM never sees raw JSON — only pre-digested facts.
"""

from __future__ import annotations
from typing import Any, Optional


def extract_facts(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Build a flat, clean facts dict from the 4 contexts.
    Keys are human-readable. Values are strings/numbers — no nested dicts.
    """
    facts: dict[str, Any] = {}

    # ── Category facts ───────────────────────────────────────
    facts["category_slug"] = category.get("slug", "unknown")
    voice = category.get("voice", {})
    facts["tone"] = voice.get("tone", "professional")
    facts["vocab_taboo"] = voice.get("vocab_taboo", [])
    facts["salutation_examples"] = voice.get("salutation_examples", [])

    peer = category.get("peer_stats", {})
    facts["peer_avg_ctr"] = peer.get("avg_ctr")
    facts["peer_avg_rating"] = peer.get("avg_rating")
    facts["peer_avg_reviews"] = peer.get("avg_review_count")

    # ── Merchant facts ───────────────────────────────────────
    # Cascade: identity sub-dict -> top-level merchant keys -> safe fallback
    identity = merchant.get("identity", {})
    facts["merchant_name"] = identity.get("name") or merchant.get("name") or "your business"
    facts["owner_first_name"] = identity.get("owner_first_name") or merchant.get("owner_first_name") or ""
    facts["city"] = identity.get("city") or merchant.get("city") or ""
    facts["locality"] = identity.get("locality") or merchant.get("locality") or ""
    facts["languages"] = identity.get("languages") or merchant.get("languages") or ["en"]
    facts["verified"] = identity.get("verified", merchant.get("verified", False))

    perf = merchant.get("performance", {})
    facts["views_30d"] = perf.get("views")
    facts["calls_30d"] = perf.get("calls")
    facts["ctr"] = perf.get("ctr")
    facts["directions_30d"] = perf.get("directions")
    facts["leads_30d"] = perf.get("leads")

    delta = perf.get("delta_7d", {})
    facts["views_delta_7d_pct"] = delta.get("views_pct")
    facts["calls_delta_7d_pct"] = delta.get("calls_pct")

    # Active offers only
    all_offers = merchant.get("offers", [])
    active_offers = [o for o in all_offers if o.get("status") == "active"]
    facts["active_offers"] = [o.get("title", "") for o in active_offers]
    facts["top_offer"] = active_offers[0].get("title", "") if active_offers else None

    cust_agg = merchant.get("customer_aggregate", {})
    facts["total_customers_ytd"] = cust_agg.get("total_unique_ytd")
    facts["lapsed_customers"] = cust_agg.get("lapsed_180d_plus", cust_agg.get("lapsed_90d_plus"))
    facts["retention_pct"] = cust_agg.get("retention_6mo_pct", cust_agg.get("retention_3mo_pct"))
    facts["high_risk_adult_count"] = cust_agg.get("high_risk_adult_count")

    facts["signals"] = merchant.get("signals", [])
    facts["subscription_status"] = merchant.get("subscription", {}).get("status")
    facts["subscription_days_remaining"] = merchant.get("subscription", {}).get("days_remaining")

    # ── Trigger facts ────────────────────────────────────────
    facts["trigger_kind"] = trigger.get("kind", "unknown")
    facts["trigger_source"] = trigger.get("source", "unknown")
    facts["trigger_urgency"] = trigger.get("urgency", 1)
    facts["trigger_scope"] = trigger.get("scope", "merchant")
    facts["suppression_key"] = trigger.get("suppression_key", "")

    # Flatten trigger payload
    payload = trigger.get("payload", {})
    facts["trigger_payload"] = payload

    # ── Trigger-kind-specific extraction ─────────────────────
    kind = trigger.get("kind", "")

    if kind == "perf_spike":
        facts["spike_metric"] = payload.get("metric", "views")
        facts["spike_delta_pct"] = payload.get("delta_pct")
        facts["spike_window"] = payload.get("window", "7d")
        facts["spike_baseline"] = payload.get("vs_baseline")
        facts["spike_driver"] = payload.get("likely_driver")

    elif kind == "perf_dip":
        facts["dip_metric"] = payload.get("metric", "views")
        facts["dip_delta_pct"] = payload.get("delta_pct")
        facts["dip_window"] = payload.get("window", "7d")
        facts["dip_baseline"] = payload.get("vs_baseline")

    elif kind == "seasonal_perf_dip":
        facts["dip_metric"] = payload.get("metric", "views")
        facts["dip_delta_pct"] = payload.get("delta_pct")
        facts["dip_window"] = payload.get("window", "7d")
        facts["season_note"] = payload.get("season_note", "")
        facts["is_expected_seasonal"] = payload.get("is_expected_seasonal", False)

    elif kind == "recall_due":
        facts["recall_service"] = payload.get("service_due", "")
        facts["recall_last_date"] = payload.get("last_service_date", "")
        facts["recall_due_date"] = payload.get("due_date", "")
        facts["recall_slots"] = payload.get("available_slots", [])

    elif kind in ("customer_lapsed_hard", "customer_lapsed_soft"):
        facts["lapse_days"] = payload.get("days_since_last_visit")
        facts["previous_focus"] = payload.get("previous_focus", "")
        facts["previous_membership_months"] = payload.get("previous_membership_months")

    elif kind == "winback_eligible":
        facts["winback_days_since_expiry"] = payload.get("days_since_expiry")
        facts["winback_perf_dip_pct"] = payload.get("perf_dip_pct")
        facts["winback_lapsed_added"] = payload.get("lapsed_customers_added_since_expiry")

    elif kind == "research_digest":
        top_item_id = payload.get("top_item_id")
        # Resolve digest item from category
        digest_items = category.get("digest", [])
        matched = [d for d in digest_items if d.get("id") == top_item_id]
        if matched:
            item = matched[0]
            facts["digest_title"] = item.get("title", "")
            facts["digest_source"] = item.get("source", "")
            facts["digest_trial_n"] = item.get("trial_n")
            facts["digest_patient_segment"] = item.get("patient_segment", "")
            facts["digest_summary"] = item.get("summary", "")
            facts["digest_actionable"] = item.get("actionable", "")
            facts["digest_kind"] = item.get("kind", "research")

    elif kind == "regulation_change":
        top_item_id = payload.get("top_item_id")
        digest_items = category.get("digest", [])
        matched = [d for d in digest_items if d.get("id") == top_item_id]
        if matched:
            item = matched[0]
            facts["regulation_title"] = item.get("title", "")
            facts["regulation_source"] = item.get("source", "")
            facts["regulation_summary"] = item.get("summary", "")
            facts["regulation_actionable"] = item.get("actionable", "")
        facts["regulation_deadline"] = payload.get("deadline_iso")

    elif kind == "supply_alert":
        facts["alert_molecule"] = payload.get("molecule", "")
        facts["alert_batches"] = payload.get("affected_batches", [])
        facts["alert_manufacturer"] = payload.get("manufacturer", "")

    elif kind == "festival_upcoming":
        facts["festival_name"] = payload.get("festival", "")
        facts["festival_date"] = payload.get("date", "")
        facts["festival_days_until"] = payload.get("days_until")

    elif kind == "competitor_opened":
        facts["competitor_name"] = payload.get("competitor_name", "")
        facts["competitor_distance_km"] = payload.get("distance_km")
        facts["competitor_offer"] = payload.get("their_offer", "")

    elif kind == "ipl_match_today":
        facts["match_teams"] = payload.get("match", "")
        facts["match_venue"] = payload.get("venue", "")
        facts["match_time"] = payload.get("match_time_iso", "")
        facts["is_weeknight"] = payload.get("is_weeknight", False)

    elif kind == "review_theme_emerged":
        facts["review_theme"] = payload.get("theme", "")
        facts["review_occurrences"] = payload.get("occurrences_30d")
        facts["review_trend"] = payload.get("trend", "")
        facts["review_quote"] = payload.get("common_quote", "")

    elif kind == "milestone_reached":
        facts["milestone_metric"] = payload.get("metric", "")
        facts["milestone_value_now"] = payload.get("value_now")
        facts["milestone_target"] = payload.get("milestone_value")
        facts["milestone_imminent"] = payload.get("is_imminent", False)

    elif kind == "active_planning_intent":
        facts["planning_topic"] = payload.get("intent_topic", "")
        facts["planning_last_message"] = payload.get("merchant_last_message", "")

    elif kind == "renewal_due":
        facts["renewal_days_remaining"] = payload.get("days_remaining")
        facts["renewal_plan"] = payload.get("plan", "")
        facts["renewal_amount"] = payload.get("renewal_amount")

    elif kind == "curious_ask_due":
        facts["ask_template"] = payload.get("ask_template", "")

    elif kind == "dormant_with_vera":
        facts["dormancy_days"] = payload.get("days_since_last_merchant_message")
        facts["last_topic"] = payload.get("last_topic", "")

    elif kind == "gbp_unverified":
        facts["verification_path"] = payload.get("verification_path", "")
        facts["estimated_uplift_pct"] = payload.get("estimated_uplift_pct")

    elif kind == "chronic_refill_due":
        facts["refill_molecules"] = payload.get("molecule_list", [])
        facts["refill_last_date"] = payload.get("last_refill", "")
        facts["refill_runs_out"] = payload.get("stock_runs_out_iso", "")
        facts["delivery_address_saved"] = payload.get("delivery_address_saved", False)

    elif kind == "category_seasonal":
        facts["season_name"] = payload.get("season", "")
        facts["seasonal_trends"] = payload.get("trends", [])

    elif kind == "cde_opportunity":
        facts["cde_credits"] = payload.get("credits")
        facts["cde_fee"] = payload.get("fee", "")
        # Resolve digest item
        dig_id = payload.get("digest_item_id")
        digest_items = category.get("digest", [])
        matched = [d for d in digest_items if d.get("id") == dig_id]
        if matched:
            item = matched[0]
            facts["cde_title"] = item.get("title", "")
            facts["cde_source"] = item.get("source", "")
            facts["cde_date"] = item.get("date", "")

    elif kind == "trial_followup":
        facts["trial_date"] = payload.get("trial_date", "")
        facts["next_session_options"] = payload.get("next_session_options", [])

    elif kind == "wedding_package_followup":
        facts["wedding_date"] = payload.get("wedding_date", "")
        facts["trial_completed"] = payload.get("trial_completed", "")
        facts["days_to_wedding"] = payload.get("days_to_wedding")
        facts["next_step_window"] = payload.get("next_step_window_open", "")

    # ── Customer facts (if present) ──────────────────────────
    if customer:
        cust_id = customer.get("identity", {})
        facts["customer_name"] = cust_id.get("name", "")
        facts["customer_language_pref"] = cust_id.get("language_pref", "english")
        facts["customer_age_band"] = cust_id.get("age_band", "")
        facts["customer_senior"] = cust_id.get("senior_citizen", False)

        rel = customer.get("relationship", {})
        facts["customer_first_visit"] = rel.get("first_visit", "")
        facts["customer_last_visit"] = rel.get("last_visit", "")
        facts["customer_visits_total"] = rel.get("visits_total", 0)
        facts["customer_services"] = rel.get("services_received", [])
        facts["customer_ltv"] = rel.get("lifetime_value", 0)
        facts["customer_fav_dish"] = rel.get("favourite_dish", "")

        facts["customer_state"] = customer.get("state", "unknown")

        prefs = customer.get("preferences", {})
        facts["customer_preferred_slots"] = prefs.get("preferred_slots", "")
        facts["customer_channel"] = prefs.get("channel", "whatsapp")
        facts["customer_reminder_opt_in"] = prefs.get("reminder_opt_in", False)
        facts["customer_training_focus"] = prefs.get("training_focus", "")
        facts["customer_wedding_date"] = prefs.get("wedding_date", "")

        consent = customer.get("consent", {})
        facts["customer_consent_scope"] = consent.get("scope", [])
        facts["customer_opted_in"] = consent.get("opted_in_at") is not None

    return facts


def get_language_instruction(languages: list[str], customer_lang_pref: str | None = None) -> str:
    """Determine the language instruction for the LLM prompt."""
    lang = customer_lang_pref if customer_lang_pref else None
    if not lang and languages:
        if "hi" in languages and "en" in languages:
            lang = "hi-en mix"
        elif "hi" in languages:
            lang = "hi"
        else:
            lang = "english"
    if not lang:
        lang = "english"

    if "hi-en" in str(lang).lower() or lang == "hi-en mix":
        return "Use natural Hindi-English code-mix (Hinglish). Example: 'Aapke liye 2 slots ready hain'."
    elif lang == "hi":
        return "Write primarily in Hindi (Devanagari optional, Roman Hindi is fine). Keep technical terms in English."
    elif "te-en" in str(lang).lower():
        return "Use English with occasional Telugu words where natural."
    elif "kn-en" in str(lang).lower():
        return "Use English with occasional Kannada words where natural."
    elif "ta-en" in str(lang).lower():
        return "Use English with occasional Tamil words where natural."
    else:
        return "Write in clear, concise English."
