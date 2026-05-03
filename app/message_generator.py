"""
Vera AI Challenge — Deterministic Message Generator
Fully template-based. FACT + IMPACT + ACTION structure.
All other fields (CTA, send_as, suppression_key) are rule-based.
"""

from __future__ import annotations
import hashlib, json, logging
from typing import Optional

from app.fact_extractor import get_language_instruction

logger = logging.getLogger(__name__)

# ── LLM response cache (hash of facts -> body) ──────────────
_cache: dict[str, str] = {}

# ── Deterministic Engine ────────────────────────────────────────────

# ── Message shape templates ──────────────────────────────────
SHAPE_TEMPLATES = {
    "perf_spike": "Structure: [FACT about spike with LOCALITY] + [REASONING — why it matters] + [ACTION-ORIENTED BINARY QUESTION (e.g. Capitalize now?)]",
    "perf_dip": "Structure: [FACT about dip with LOCALITY] + [REASONING — likely impact on bookings/revenue] + [ACTION-ORIENTED BINARY QUESTION (e.g. Fix visibility now?)]",
    "seasonal_perf_dip": "Structure: [FACT about seasonal dip with LOCALITY] + [REASONING — what competitors are doing] + [ACTION-ORIENTED BINARY QUESTION (e.g. Activate offer?)]",
    "recall_due": "Structure: [FACT — time since last visit] + [REASONING — why they need to return] + [ACTION-ORIENTED BINARY QUESTION (e.g. Book slot now?)]",
    "customer_lapsed_hard": "Structure: [FACT — time lapsed] + [REASONING — missing out on specific new offering] + [ACTION-ORIENTED BINARY QUESTION (e.g. Claim trial offer?)]",
    "customer_lapsed_soft": "Structure: [FACT — time since last visit] + [REASONING — benefits of returning] + [ACTION-ORIENTED BINARY QUESTION (e.g. Secure slot?)]",
    "winback_eligible": "Structure: [FACT — absence duration] + [REASONING — impact of missing out] + [ACTION-ORIENTED BINARY QUESTION (e.g. Restart now?)]",
    "research_digest": "Structure: [FACT — specific journal finding] + [REASONING — relevance to their specific practice/locality] + [ACTION-ORIENTED BINARY QUESTION (e.g. Apply to practice?)]",
    "regulation_change": "Structure: [FACT — regulation change with deadline] + [REASONING — compliance risk] + [ACTION-ORIENTED BINARY QUESTION (e.g. Start audit now?)]",
    "supply_alert": "Structure: [FACT — urgent supply flag for specific batches] + [REASONING — impact on affected customers] + [ACTION-ORIENTED BINARY QUESTION (e.g. Draft notifications?)]",
    "competitor_opened": "Structure: [FACT — new competitor distance] + [REASONING — threat to footfall] + [ACTION-ORIENTED BINARY QUESTION (e.g. Launch counter-offer?)]",
    "festival_upcoming": "Structure: [FACT — festival days away] + [REASONING — expected demand surge] + [ACTION-ORIENTED BINARY QUESTION (e.g. Prepare inventory?)]",
    "ipl_match_today": "Structure: [FACT — match details] + [REASONING — opportunity for targeted promos] + [ACTION-ORIENTED BINARY QUESTION (e.g. Create content now?)]",
    "review_theme_emerged": "Structure: [FACT — review theme occurrences] + [REASONING — impact on reputation] + [ACTION-ORIENTED BINARY QUESTION (e.g. Address it now?)]",
    "milestone_reached": "Structure: [FACT — milestone numbers] + [REASONING — momentum opportunity] + [ACTION-ORIENTED BINARY QUESTION (e.g. Promote milestone?)]",
    "active_planning_intent": "Structure: [FACT — plan details ready] + [REASONING — next immediate benefit] + [ACTION-ORIENTED BINARY QUESTION (e.g. Execute step 1?)]",
    "renewal_due": "Structure: [FACT — days to renewal] + [REASONING — value delivered so far] + [ACTION-ORIENTED BINARY QUESTION (e.g. Renew now?)]",
    "curious_ask_due": "Structure: [FACT — specific metric or trend observed] + [REASONING — why we need to know] + [ACTION-ORIENTED BINARY QUESTION (e.g. Share details?)]",
    "dormant_with_vera": "Structure: [FACT — one specific new relevant thing] + [REASONING — why it fits them] + [ACTION-ORIENTED BINARY QUESTION (e.g. Explore this?)]",
    "gbp_unverified": "Structure: [FACT — profile unverified] + [REASONING — estimated uplift lost] + [ACTION-ORIENTED BINARY QUESTION (e.g. Verify now?)]",
    "chronic_refill_due": "Structure: [FACT — run-out date for medicines] + [REASONING — health continuity] + [ACTION-ORIENTED BINARY QUESTION (e.g. Confirm delivery?)]",
    "category_seasonal": "Structure: [FACT — seasonal trend numbers] + [REASONING — risk of missing out] + [ACTION-ORIENTED BINARY QUESTION (e.g. Adjust shelf now?)]",
    "cde_opportunity": "Structure: [FACT — event credits available] + [REASONING — relevance to their specialty] + [ACTION-ORIENTED BINARY QUESTION (e.g. Register now?)]",
    "trial_followup": "Structure: [FACT — trial completion] + [REASONING — next logical progression] + [ACTION-ORIENTED BINARY QUESTION (e.g. Book next session?)]",
    "wedding_package_followup": "Structure: [FACT — days to wedding] + [REASONING — current prep window closing] + [ACTION-ORIENTED BINARY QUESTION (e.g. Secure package?)]",
}

# ── Category style rules ─────────────────────────────────────
CATEGORY_STYLE = {
    "dentists": "Tone: peer-clinical, collegial. Use technical dental vocabulary naturally. Address as 'Dr. {name}'. NO hype, NO promotional language, NO 'amazing/incredible'. Cite sources when referencing research.",
    "salons": "Tone: warm, friendly, practical, fellow-business-owner. Use beauty/styling vocabulary. Address by first name. Light emoji OK. Focus on actionable business advice.",
    "restaurants": "Tone: operator-to-operator, practical. Use restaurant vocabulary (covers, AOV, footfall). Address by first name. Data-driven suggestions.",
    "gyms": "Tone: coaching, motivational but grounded. Use fitness vocabulary. No shame or guilt-trip for customer-facing. Address by first name.",
    "pharmacies": "Tone: trustworthy, precise, compliance-aware. Use pharmaceutical vocabulary correctly (molecule names, batch numbers). Senior-respectful for elderly customers.",
}


def _build_cache_key(facts: dict) -> str:
    """Deterministic hash of the facts dict for caching."""
    serialized = json.dumps(facts, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def generate_message_body(
    facts: dict,
    category: dict,
    trigger_kind: str,
    cta_type: str,
    send_as: str,
    customer: Optional[dict] = None,
) -> str:
    """
    Generate the message body deterministically.
    """
    return _fallback_body(facts, trigger_kind, send_as)


def generate_reply_body(
    facts: dict,
    category: dict,
    merchant_message: str,
    intent: str,
    conversation_history: list[str],
) -> str:
    """Generate a reply body for a merchant/customer response deterministically."""
    owner = _safe(facts.get("owner_first_name"))
    merchant_name = _safe(facts.get("merchant_name"))
    addr = owner or merchant_name or "there"
    trigger_kind = _safe(facts.get("trigger_kind"))
    locality = _safe(facts.get("locality"), _safe(facts.get("city"), "your area"))

    if intent == "confirm":
        # Context-aware action confirmation
        if trigger_kind == "perf_dip":
            offer = _offer_phrase(facts)
            return f"On it, {addr}. I'm activating {offer} and optimizing your listing for {locality} — you should see traction within 48 hours."
        if trigger_kind == "active_planning_intent":
            topic = _safe(facts.get("planning_topic"), "the plan")
            return f"Great, {addr}. Drafting the {topic.replace('_', ' ')} outline now — will share it for your review shortly."
        if trigger_kind == "renewal_due":
            return f"Done, {addr}. Processing your renewal now — your listing stays live with zero downtime."
        return f"Done — working on it now, {addr}. Will share the draft shortly."

    elif intent == "question":
        # Use facts to answer where possible
        views = _safe(facts.get("views_30d"))
        ctr = _safe(facts.get("ctr"))
        if views and ctr:
            return (f"Good question, {addr}. Based on your current data: {views} views and {ctr} CTR this month in {locality}. "
                    f"Let me pull more detail and get back to you.")
        return f"Good question, {addr}. Let me check the latest data for {locality} and get back to you with specifics."

    else:
        # General — advance conversation
        return f"Got it, {addr}. Based on what I'm seeing for {locality}, here's what I'd suggest as a next step."


def _build_prompt(
    facts: dict, category: dict, trigger_kind: str,
    cta_type: str, send_as: str, customer: Optional[dict],
) -> str:
    """Build the full Gemini prompt with shape template and category style."""
    slug = facts.get("category_slug", "unknown")
    style = CATEGORY_STYLE.get(slug, "Tone: professional and helpful.")
    shape = SHAPE_TEMPLATES.get(trigger_kind, "Structure: [RELEVANT FACT] + [ACTION or OFFER] + [end with a question]")

    lang_pref = facts.get("customer_language_pref") if customer else None
    lang_instr = get_language_instruction(facts.get("languages", ["en"]), lang_pref)

    # Determine addressing
    if send_as == "merchant_on_behalf" and customer:
        cust_name = facts.get("customer_name", "")
        merchant_name = facts.get("merchant_name", "")
        addressing = f"Address the customer as '{cust_name}'. Sign as '{merchant_name}'."
    else:
        owner = facts.get("owner_first_name", "")
        salutations = facts.get("salutation_examples", [])
        if salutations and owner:
            sal = salutations[0].replace("{first_name}", owner)
            addressing = f"Address the merchant as '{sal}'."
        elif owner:
            addressing = f"Address the merchant by first name: '{owner}'."
        else:
            addressing = f"Address as '{facts.get('merchant_name', 'there')}'."

    facts_block = _format_facts_for_prompt(facts)
    taboos = facts.get("vocab_taboo", [])
    taboo_str = ", ".join(taboos[:8]) if taboos else "none"

    prompt = f"""You are Vera, a merchant engagement AI. Generate ONLY the message body.

CATEGORY STYLE: {style}
LANGUAGE: {lang_instr}
MESSAGE SHAPE: {shape}
{addressing}

FACTS (use these — do NOT invent data):
{facts_block}

CONSTRAINTS:
- TABOO WORDS (never use): {taboo_str}
- Maximum 4-5 sentences. Be concise.
- Include at least one specific number or fact from the data above.
- Do NOT include a CTA line — the CTA is appended separately.
- Do NOT use URLs.
- START IMMEDIATELY WITH A FACT OR SIGNAL. Do NOT use greetings like "Hi Name" or "Hello" or "I have an update".
- Embed the merchant's locality, active offers, or performance natively in the first sentence.
- Include REASONING inside the message (e.g. "likely affecting bookings").
- END WITH AN ACTION-ORIENTED BINARY CTA (e.g. "Activate offer?", "Fix listing now?"). Do NOT use weak CTAs like "Want me to look into it?".
- Do NOT fabricate statistics, competitor names, or research not in the facts.

Write ONLY the message body, nothing else:"""

    return prompt


def _format_facts_for_prompt(facts: dict) -> str:
    """Format the facts dict into a clean text block for the prompt."""
    lines = []
    skip_keys = {"vocab_taboo", "salutation_examples", "trigger_payload", "signals"}

    for key, val in facts.items():
        if key in skip_keys or val is None or val == "" or val == []:
            continue
        if isinstance(val, list):
            if len(val) > 5:
                val = val[:5]
            val = ", ".join(str(v) for v in val)
        if isinstance(val, dict):
            val = json.dumps(val, default=str)
        lines.append(f"- {key}: {val}")

    return "\n".join(lines)


# ── Null-safe helpers ────────────────────────────────────────

def _safe(val, fallback: str = "") -> str:
    """Return val as string if truthy, else fallback. Never returns 'None'."""
    if val is None or val == "" or val == [] or val == "None":
        return fallback
    return str(val)


def _pct(val) -> str:
    """Convert a decimal like -0.50 or 0.25 to '50%' or '25%'."""
    if val is None:
        return "noticeably"
    try:
        return f"{int(abs(float(val)) * 100)}%"
    except (ValueError, TypeError):
        return "noticeably"


def _addr(facts: dict, send_as: str) -> tuple[str, str]:
    """Return (display_name, locality) safe for interpolation."""
    if send_as == "merchant_on_behalf":
        n = _safe(facts.get("customer_name"), _safe(facts.get("merchant_name"), "there"))
    else:
        n = _safe(facts.get("owner_first_name"), _safe(facts.get("merchant_name"), "there"))
    loc = _safe(facts.get("locality"), _safe(facts.get("city"), "your area"))
    return n, loc


def _loc_phrase(locality: str) -> str:
    """Return ' in {locality}' only if locality is a real place, not a fallback."""
    if locality and locality != "your area":
        return f" in {locality}"
    return ""


import re

def _saluted_name(facts: dict, send_as: str) -> str:
    """Return the properly saluted name based on category conventions."""
    if send_as == "merchant_on_behalf":
        return _safe(facts.get("customer_name"), "there")
    
    owner = _safe(facts.get("owner_first_name"))
    salutations = facts.get("salutation_examples", [])
    
    if salutations and owner:
        # e.g. "Dr. {first_name}" -> "Dr. Meera", "Hi {pharmacist_name}" -> "Hi Ramesh"
        return re.sub(r'\{.*?\}', owner, salutations[0])
    
    return owner or _safe(facts.get("merchant_name"), "there")


def _offer_phrase(facts: dict) -> str:
    """Return the top active offer or a generic phrase — never None."""
    offer = _safe(facts.get("top_offer"))
    if offer:
        return offer
    offers = facts.get("active_offers", [])
    if offers and offers[0]:
        return str(offers[0])
    return "a targeted offer"


# ── Deterministic message templates ──────────────────────────

def _fallback_body(facts: dict, trigger_kind: str, send_as: str) -> str:
    """
    Deterministic, template-based message generator.
    Structure: FACT + IMPACT + ACTION for every trigger kind.
    All values are null-safe — no 'None' or broken sentences.
    """
    _, locality = _addr(facts, send_as)
    name = _saluted_name(facts, send_as)
    loc_phrase = _loc_phrase(locality)
    
    cust_name = _safe(facts.get("customer_name"))
    merchant_name = _safe(facts.get("merchant_name"), "your business")

    # ── Customer-scoped: personalized with time gap & behavior ──
    if send_as == "merchant_on_behalf" and cust_name:
        lapse_days = _safe(facts.get("lapse_days"))
        services = facts.get("customer_services", [])
        last_service = services[-1] if services else ""
        fav_dish = _safe(facts.get("customer_fav_dish"))

        if trigger_kind == "recall_due":
            service = _safe(facts.get("recall_service"), "your scheduled visit")
            slots = facts.get("recall_slots", [])
            slot_label = slots[0].get("label", "this week") if slots else "this week"
            return (f"{cust_name}, your {service} is coming up and we have a slot available on {slot_label}. "
                    f"Staying on schedule keeps your results on track. Book now?")

        if trigger_kind == "customer_lapsed_hard":
            gap = f"It's been {lapse_days} days since your last visit" if lapse_days else "It's been a while"
            focus = _safe(facts.get("previous_focus"))
            hook = f" — we have a new program for {focus} that fits your goals" if focus else " — we have some fresh options you might like"
            return f"{cust_name}, {gap.lower()}{hook}. Claim a trial session?"

        if trigger_kind == "customer_lapsed_soft":
            gap = f"It's been {lapse_days} days" if lapse_days else "It's been a little while"
            hook = f" Your {last_service} results are best maintained with regular visits." if last_service else ""
            return f"{cust_name}, {gap.lower()} since we last saw you.{hook} Secure your preferred slot?"

        if trigger_kind == "chronic_refill_due":
            mols = facts.get("refill_molecules", [])
            mol_str = ", ".join(mols[:3]) if mols else "your regular medicines"
            runout = _safe(facts.get("refill_runs_out"), "soon")
            return (f"{cust_name}, your supply of {mol_str} is estimated to run out by {runout}. "
                    f"Continuity matters for your health. Confirm home delivery?")

        if trigger_kind == "trial_followup":
            trial_date = _safe(facts.get("trial_date"), "recently")
            options = facts.get("next_session_options", [])
            slot_str = options[0].get("label", "this week") if options else "this week"
            return (f"{cust_name}, great that you completed your trial on {trial_date}. "
                    f"The next session is available on {slot_str} — continuing now locks in your momentum. Book next session?")

        if trigger_kind == "wedding_package_followup":
            days_to = _safe(facts.get("days_to_wedding"))
            window = _safe(facts.get("next_step_window"), "the next prep phase")
            time_note = f"With {days_to} days to the wedding" if days_to else "With the wedding approaching"
            return (f"{cust_name}, {time_note}, now is the ideal time to start {window}. "
                    f"Early booking ensures your preferred dates. Secure your package?")

        # Generic customer fallback — personalized
        if fav_dish:
            return f"{cust_name}, we thought of you — your favourite ({fav_dish}) pairs well with what's new this week. Check it out?"
        if lapse_days:
            return f"{cust_name}, it's been {lapse_days} days since your last visit — getting back now helps maintain your progress. Would you like to take a look?"
        return f"{cust_name}, we have something new that matches your preferences. Would you like to take a look?"

    # ── Merchant-scoped templates ────────────────────────────

    if trigger_kind == "perf_spike":
        metric = _safe(facts.get("spike_metric"), "engagement")
        delta = _pct(facts.get("spike_delta_pct"))
        driver = _safe(facts.get("spike_driver"))
        driver_note = f", likely driven by {driver}" if driver else ""
        offer = _offer_phrase(facts)
        return (f"{name}, your {metric}{loc_phrase} jumped {delta} this week{driver_note} — "
                f"strong demand is building and converting this now can increase bookings. "
                f"Activate {offer}?")

    if trigger_kind == "perf_dip":
        metric = _safe(facts.get("dip_metric"), "engagement")
        delta = _pct(facts.get("dip_delta_pct"))
        baseline = _safe(facts.get("dip_baseline"))
        baseline_note = f" (down from {baseline})" if baseline else ""
        offer = _offer_phrase(facts)
        return (f"{name}, your {metric}{loc_phrase} dropped {delta} this week{baseline_note} — "
                f"this likely means fewer bookings reaching you. "
                f"Activating {offer} can recover visibility fast. Fix it now?")

    if trigger_kind == "seasonal_perf_dip":
        metric = _safe(facts.get("dip_metric"), "traffic")
        delta = _pct(facts.get("dip_delta_pct"))
        season = _safe(facts.get("season_note"), "this seasonal cycle")
        return (f"{name}, your {metric}{loc_phrase} is down {delta} — consistent with {season}. "
                f"Competitors typically push offers during this window. Activate a counter-offer?")

    if trigger_kind == "recall_due":
        service = _safe(facts.get("recall_service"), "scheduled appointment")
        return f"{name}, a patient recall for {service} is due this week — timely follow-up improves retention and outcomes. Send reminders now?"

    if trigger_kind == "winback_eligible":
        days = _safe(facts.get("winback_days_since_expiry"), "over a month")
        dip = _pct(facts.get("winback_perf_dip_pct"))
        lapsed = _safe(facts.get("winback_lapsed_added"), "several")
        return (f"{name}, it's been {days} days since your subscription expired and performance has dipped {dip}. "
                f"Meanwhile, {lapsed} customers have moved to lapsed status. Reactivating now stops the bleed. Restart?")

    if trigger_kind == "renewal_due":
        days_left = _safe(facts.get("renewal_days_remaining"), "a few")
        plan = _safe(facts.get("renewal_plan"), "your current plan")
        amount = _safe(facts.get("renewal_amount"))
        price_note = f" at {amount}" if amount else ""
        return (f"{name}, your {plan} subscription renews in {days_left} days{price_note}. "
                f"Renewing on time ensures zero disruption to your listing visibility. Renew now?")

    if trigger_kind == "competitor_opened":
        comp = _safe(facts.get("competitor_name"), "a new competitor")
        dist = _safe(facts.get("competitor_distance_km"))
        comp_offer = _safe(facts.get("competitor_offer"))
        dist_note = f" just {dist} km away" if dist else " nearby"
        offer_note = f" — they're promoting {comp_offer}" if comp_offer else ""
        your_offer = _offer_phrase(facts)
        return (f"{name}, {comp} opened{dist_note}{loc_phrase}{offer_note}. "
                f"A strong counter-offer like {your_offer} now can protect your footfall. Launch one?")

    if trigger_kind == "festival_upcoming":
        fest = _safe(facts.get("festival_name"), "an upcoming festival")
        days_until = _safe(facts.get("festival_days_until"))
        time_note = f" is {days_until} days away" if days_until else " is approaching"
        return (f"{name}, {fest}{time_note} — demand surges are already showing{loc_phrase}. "
                f"Early prep gives you the edge over competitors. Start planning your festival push?")

    if trigger_kind == "ipl_match_today":
        match = _safe(facts.get("match_teams"), "today's IPL match")
        venue = _safe(facts.get("match_venue"), "a nearby venue")
        return (f"{name}, {match} is live at {venue} tonight — match nights drive 20-40% more footfall{loc_phrase}. "
                f"A same-day offer can capture that traffic. Push a match-night special?")

    if trigger_kind == "review_theme_emerged":
        theme = _safe(facts.get("review_theme"), "a recurring topic")
        count = _safe(facts.get("review_occurrences"), "multiple")
        quote = _safe(facts.get("review_quote"))
        quote_note = f' One customer said: "{quote}".' if quote else ""
        return (f'{name}, "{theme}" appeared in {count} reviews this month{loc_phrase}.{quote_note} '
                f"Addressing this now protects your rating. Tackle it?")

    if trigger_kind == "milestone_reached":
        metric = _safe(facts.get("milestone_metric"), "a key metric")
        val = _safe(facts.get("milestone_value_now"), "close")
        target = _safe(facts.get("milestone_target"))
        target_note = f" — just {int(float(target) - float(val))} away from {target}" if target and val and val != "close" else ""
        return (f"{name}, your {metric}{loc_phrase} hit {val}{target_note}. "
                f"Sharing this milestone builds trust and attracts new customers. Shall we post a thank-you note to your profile?")

    if trigger_kind == "active_planning_intent":
        topic = _safe(facts.get("planning_topic"), "your business initiative")
        return (f"{name}, building on your {topic.replace('_', ' ')} plan — I've outlined the next steps. "
                f"Moving quickly captures the demand window. Ready to execute step one?")

    if trigger_kind == "research_digest":
        title = _safe(facts.get("digest_title"), "a new research finding")
        source = _safe(facts.get("digest_source"))
        source_note = f" ({source})" if source else ""
        actionable = _safe(facts.get("digest_actionable"))
        segment = _safe(facts.get("digest_patient_segment"))
        segment_note = f" — particularly for your {segment} patients" if segment else ""
        action_note = f" Suggested action: {actionable}." if actionable else ""
        return (f"{name}, new finding{source_note}: {title}{segment_note}.{action_note} "
                f"Want me to flag the affected patients in your list?")

    if trigger_kind == "regulation_change":
        title = _safe(facts.get("regulation_title"), "a regulatory update")
        deadline = _safe(facts.get("regulation_deadline"))
        deadline_note = f" Compliance deadline: {deadline}." if deadline else ""
        actionable = _safe(facts.get("regulation_actionable"))
        action_note = f" Required action: {actionable}." if actionable else ""
        return (f"{name}, heads up — {title}.{deadline_note}{action_note} "
                f"Non-compliance risks penalties and disruption. Start your audit now?")

    if trigger_kind == "supply_alert":
        molecule = _safe(facts.get("alert_molecule"), "a critical product")
        batches = facts.get("alert_batches", [])
        batch_str = ", ".join(batches[:3]) if batches else "affected batches"
        mfr = _safe(facts.get("alert_manufacturer"))
        mfr_note = f" from {mfr}" if mfr else ""
        return (f"{name}, urgent: {molecule}{mfr_note} — batches {batch_str} flagged for recall. "
                f"Affected customers need immediate notification. Draft alerts now to prevent safety issues?")

    if trigger_kind == "curious_ask_due":
        template = _safe(facts.get("ask_template"), "business_trend")
        question = template.replace("_", " ")
        return (f"{name}, quick one — I'm tracking {question} trends for businesses{loc_phrase}. "
                f"Your input helps me tailor better insights for you. Share your take?")

    if trigger_kind == "dormant_with_vera":
        days = _safe(facts.get("dormancy_days"), "a while")
        topic = _safe(facts.get("last_topic"), "our last conversation")
        return (f"{name}, it's been {days} days since we last connected about {topic.replace('_', ' ')}. "
                f"I have fresh data on your market{loc_phrase} that's worth a look. Explore this?")

    if trigger_kind == "gbp_unverified":
        uplift = _pct(facts.get("estimated_uplift_pct"))
        path = _safe(facts.get("verification_path"), "a quick phone call")
        return (f"{name}, your business profile is still unverified — verified listings see up to {uplift} more engagement. "
                f"The process takes just {path}. Verify now?")

    if trigger_kind == "chronic_refill_due":
        mols = facts.get("refill_molecules", [])
        mol_str = ", ".join(mols[:3]) if mols else "regular prescriptions"
        runout = _safe(facts.get("refill_runs_out"), "soon")
        return (f"{name}, a patient's {mol_str} supply runs out around {runout}. "
                f"Proactive refill reminders improve adherence and retention. Send reminder?")

    if trigger_kind == "category_seasonal":
        season = _safe(facts.get("season_name"), "the current season")
        trends = facts.get("seasonal_trends", [])
        trend_str = ", ".join(str(t) for t in trends[:3]) if trends else "shifting demand patterns"
        return (f"{name}, {season.replace('_', ' ')} is driving shifts{loc_phrase}: {trend_str}. "
                f"Adjusting your inventory now captures early demand. Review your shelf mix?")

    if trigger_kind == "cde_opportunity":
        title = _safe(facts.get("cde_title"), "an upcoming professional event")
        credits = _safe(facts.get("cde_credits"))
        fee = _safe(facts.get("cde_fee"), "details available")
        credit_note = f" ({credits} CDE credits, {fee})" if credits else ""
        return (f"{name}, {title}{credit_note} — relevant to practitioners{loc_phrase}. "
                f"Staying current strengthens both your skills and patient trust. Register?")

    if trigger_kind == "customer_lapsed_hard":
        lapse = _safe(facts.get("lapse_days"))
        focus = _safe(facts.get("previous_focus"))
        gap = f"A member hasn't visited in {lapse} days" if lapse else "A member has been away for a while"
        hook = f" — their focus was {focus}, and you have new options in that area" if focus else ""
        return f"{name}, {gap.lower()}{hook}. A personalized win-back message can re-engage them. Send one?"

    if trigger_kind == "customer_lapsed_soft":
        return f"{name}, a few customers are showing early lapse signals{loc_phrase}. A timely check-in keeps them engaged. Send a reminder?"

    if trigger_kind == "trial_followup":
        trial_date = _safe(facts.get("trial_date"), "recently")
        return f"{name}, a trial customer from {trial_date} hasn't booked their next session yet — following up within 7 days doubles conversion. Send a follow-up?"

    if trigger_kind == "wedding_package_followup":
        days_to = _safe(facts.get("days_to_wedding"))
        time_note = f"With {days_to} days until the wedding" if days_to else "With the wedding approaching"
        return f"{name}, {time_note}, your bridal client is entering the prep window. Early scheduling locks in their loyalty and your revenue. Reach out?"

    # ── Unknown / unhandled trigger — meaningful analysis fallback ──
    views = _safe(facts.get("views_30d"))
    offer = _offer_phrase(facts)
    loc_note = f" in {locality}" if locality else ""
    if views:
        return (f"{name}, we detected unusual activity on your listing{loc_phrase} — {views} views this month "
                f"with room to improve conversions. Want me to share specific insights?")
    return (f"{name}, we've been analyzing your listing data{loc_phrase} and identified ways to improve visibility and conversions. "
            f"Want me to share a quick analysis with actionable next steps?")
