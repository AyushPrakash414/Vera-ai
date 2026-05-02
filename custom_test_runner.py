#!/usr/bin/env python3
"""
Vera AI Challenge — Custom Test Runner
=======================================
Tests the /v1/tick endpoint with diverse synthetic scenarios.
Pushes required contexts first, then fires tick and displays results.

Usage:  python custom_test_runner.py
"""

import requests, json, time, sys, copy
from datetime import datetime, timezone

BASE_URL = "http://localhost:8080"
VERSION = 1  # must match judge's version (1) so category pushes are idempotent

# Unique per-run suffix so suppression/cooldown never blocks re-runs
RUN_ID = str(int(time.time()))[-6:]

# ═══════════════════════════════════════════════════════════════
# MINIMAL CATEGORY TEMPLATES (one per type)
# ═══════════════════════════════════════════════════════════════

CATEGORIES = {
    "dentists": {
        "slug": "dentists",
        "voice": {"tone": "peer_clinical", "vocab_taboo": ["guaranteed", "miracle"], "salutation_examples": ["Dr. {first_name}"]},
        "peer_stats": {"avg_ctr": 0.030, "avg_rating": 4.4, "avg_review_count": 62},
        "digest": [],
    },
    "salons": {
        "slug": "salons",
        "voice": {"tone": "warm_friendly", "vocab_taboo": ["ugly", "old-looking"], "salutation_examples": ["{first_name}"]},
        "peer_stats": {"avg_ctr": 0.045, "avg_rating": 4.2, "avg_review_count": 80},
        "digest": [],
    },
    "restaurants": {
        "slug": "restaurants",
        "voice": {"tone": "operator_practical", "vocab_taboo": ["unhygienic"], "salutation_examples": ["{first_name}"]},
        "peer_stats": {"avg_ctr": 0.028, "avg_rating": 4.1, "avg_review_count": 120},
        "digest": [],
    },
    "gyms": {
        "slug": "gyms",
        "voice": {"tone": "coaching", "vocab_taboo": ["fat", "lazy"], "salutation_examples": ["{first_name}"]},
        "peer_stats": {"avg_ctr": 0.050, "avg_rating": 4.3, "avg_review_count": 55},
        "digest": [],
    },
    "pharmacies": {
        "slug": "pharmacies",
        "voice": {"tone": "trustworthy_precise", "vocab_taboo": ["cure-all"], "salutation_examples": ["{first_name}"]},
        "peer_stats": {"avg_ctr": 0.040, "avg_rating": 4.5, "avg_review_count": 45},
        "digest": [],
    },
}

# ═══════════════════════════════════════════════════════════════
# HELPER: build a merchant dict
# ═══════════════════════════════════════════════════════════════

def make_merchant(mid, cat_slug, name, owner, city, locality, views=1000, calls=10, ctr=0.03,
                  offers=None, sub_status="active", sub_days=90, signals=None):
    return {
        "merchant_id": mid,
        "category_slug": cat_slug,
        "identity": {
            "name": name, "owner_first_name": owner, "city": city, "locality": locality,
            "verified": True, "languages": ["en", "hi"],
        },
        "subscription": {"status": sub_status, "plan": "Pro", "days_remaining": sub_days},
        "performance": {
            "window_days": 30, "views": views, "calls": calls, "directions": 30,
            "ctr": ctr, "leads": 5, "delta_7d": {"views_pct": -0.10, "calls_pct": -0.10},
        },
        "offers": offers or [],
        "customer_aggregate": {"total_unique_ytd": 200, "lapsed_180d_plus": 40, "retention_6mo_pct": 0.35},
        "signals": signals or [],
        "conversation_history": [],
    }

def make_customer(cid, mid, name, phone="<phone>", consent=True, channel="whatsapp"):
    return {
        "customer_id": cid, "merchant_id": mid,
        "identity": {"name": name, "phone_redacted": phone, "language_pref": "english", "age_band": "25-35"},
        "relationship": {"first_visit": "2025-06-01", "last_visit": "2026-03-01", "visits_total": 5,
                         "services_received": ["service_a"], "lifetime_value": 2000},
        "state": "lapsed_soft",
        "preferences": {"preferred_slots": "weekday_evening", "channel": channel, "reminder_opt_in": consent},
        "consent": {"opted_in_at": "2025-06-01" if consent else None, "scope": ["recall_reminders"] if consent else []},
    }

# ═══════════════════════════════════════════════════════════════
# TEST CASE DEFINITIONS
# ═══════════════════════════════════════════════════════════════

TEST_CASES = [
    # 1. perf_dip 20% — restaurant
    {
        "name": "Perf Dip 20% — Restaurant",
        "merchant": make_merchant("ct_m01", "restaurants", "Tandoor Express", "Raj", "Delhi", "Connaught Place",
                                  views=3000, calls=25, offers=[{"id":"o1","title":"Lunch Thali @ ₹199","status":"active","started":"2026-03-01"}]),
        "trigger": {
            "id": "ct_trg01", "scope": "merchant", "kind": "perf_dip", "source": "internal",
            "merchant_id": "ct_m01", "customer_id": None,
            "payload": {"metric": "calls", "delta_pct": -0.20, "window": "7d", "vs_baseline": 25},
            "urgency": 3, "suppression_key": "ct_test_01", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 2. perf_dip 50% — dentist
    {
        "name": "Perf Dip 50% — Dentist",
        "merchant": make_merchant("ct_m02", "dentists", "SmileCare Clinic", "Arjun", "Mumbai", "Bandra West",
                                  views=900, calls=4, signals=["perf_dip_severe"]),
        "trigger": {
            "id": "ct_trg02", "scope": "merchant", "kind": "perf_dip", "source": "internal",
            "merchant_id": "ct_m02", "customer_id": None,
            "payload": {"metric": "views", "delta_pct": -0.50, "window": "7d", "vs_baseline": 900},
            "urgency": 4, "suppression_key": "ct_test_02", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 3. perf_dip 80% — gym (severe)
    {
        "name": "Perf Dip 80% — Gym (Severe)",
        "merchant": make_merchant("ct_m03", "gyms", "Iron Temple", "Vikram", "Bangalore", "Koramangala",
                                  views=500, calls=2, signals=["perf_dip_severe"]),
        "trigger": {
            "id": "ct_trg03", "scope": "merchant", "kind": "perf_dip", "source": "internal",
            "merchant_id": "ct_m03", "customer_id": None,
            "payload": {"metric": "calls", "delta_pct": -0.80, "window": "7d", "vs_baseline": 10},
            "urgency": 5, "suppression_key": "ct_test_03", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 4. perf_spike — salon
    {
        "name": "Perf Spike +40% — Salon",
        "merchant": make_merchant("ct_m04", "salons", "Glow Studio", "Priya", "Hyderabad", "Jubilee Hills",
                                  views=5000, calls=60, signals=["growing_views_7d"]),
        "trigger": {
            "id": "ct_trg04", "scope": "merchant", "kind": "perf_spike", "source": "internal",
            "merchant_id": "ct_m04", "customer_id": None,
            "payload": {"metric": "views", "delta_pct": 0.40, "window": "7d", "vs_baseline": 3500, "likely_driver": "reel_viral"},
            "urgency": 2, "suppression_key": "ct_test_04", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 5. perf_spike — pharmacy
    {
        "name": "Perf Spike +25% — Pharmacy",
        "merchant": make_merchant("ct_m05", "pharmacies", "HealthFirst Pharmacy", "Ramesh", "Jaipur", "C-Scheme",
                                  views=2000, calls=40),
        "trigger": {
            "id": "ct_trg05", "scope": "merchant", "kind": "perf_spike", "source": "internal",
            "merchant_id": "ct_m05", "customer_id": None,
            "payload": {"metric": "calls", "delta_pct": 0.25, "window": "7d", "vs_baseline": 32},
            "urgency": 1, "suppression_key": "ct_test_05", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 6. recall_due — customer-scoped (dentist)
    {
        "name": "Recall Due — Customer (Dentist)",
        "merchant": make_merchant("ct_m06", "dentists", "Dr. Neha Dental", "Neha", "Chennai", "T. Nagar"),
        "customer": make_customer("ct_c06", "ct_m06", "Ravi"),
        "trigger": {
            "id": "ct_trg06", "scope": "customer", "kind": "recall_due", "source": "internal",
            "merchant_id": "ct_m06", "customer_id": "ct_c06",
            "payload": {"service_due": "6_month_cleaning", "last_service_date": "2025-11-01", "due_date": "2026-05-01",
                        "available_slots": [{"iso": "2026-05-05T18:00:00+05:30", "label": "Mon 5 May, 6pm"}]},
            "urgency": 3, "suppression_key": "ct_test_06", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 7. winback_eligible — salon
    {
        "name": "Winback Eligible — Salon",
        "merchant": make_merchant("ct_m07", "salons", "Luxe Salon", "Anjali", "Pune", "Koregaon Park",
                                  sub_status="expired", sub_days=0, signals=["winback_eligible"]),
        "trigger": {
            "id": "ct_trg07", "scope": "merchant", "kind": "winback_eligible", "source": "internal",
            "merchant_id": "ct_m07", "customer_id": None,
            "payload": {"days_since_expiry": 45, "perf_dip_pct": -0.35, "lapsed_customers_added_since_expiry": 30},
            "urgency": 2, "suppression_key": "ct_test_07", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 8. customer_lapsed_hard — gym
    {
        "name": "Customer Lapsed Hard — Gym",
        "merchant": make_merchant("ct_m08", "gyms", "FitZone", "Karthik", "Bangalore", "HSR Layout"),
        "customer": make_customer("ct_c08", "ct_m08", "Sneha"),
        "trigger": {
            "id": "ct_trg08", "scope": "customer", "kind": "customer_lapsed_hard", "source": "internal",
            "merchant_id": "ct_m08", "customer_id": "ct_c08",
            "payload": {"days_since_last_visit": 65, "previous_focus": "cardio", "previous_membership_months": 4},
            "urgency": 3, "suppression_key": "ct_test_08", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 9. festival_upcoming — restaurant
    {
        "name": "Festival Upcoming — Restaurant",
        "merchant": make_merchant("ct_m09", "restaurants", "Spice Route", "Suresh", "Delhi", "Karol Bagh",
                                  offers=[{"id":"o9","title":"Family Dinner @ ₹999","status":"active","started":"2026-04-01"}]),
        "trigger": {
            "id": "ct_trg09", "scope": "merchant", "kind": "festival_upcoming", "source": "external",
            "merchant_id": "ct_m09", "customer_id": None,
            "payload": {"festival": "Navratri", "date": "2026-10-02", "days_until": 153},
            "urgency": 1, "suppression_key": "ct_test_09", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 10. unknown trigger type (edge case)
    {
        "name": "Unknown Trigger Type (Edge Case)",
        "merchant": make_merchant("ct_m10", "restaurants", "Chai Point", "Deepak", "Mumbai", "Lower Parel"),
        "trigger": {
            "id": "ct_trg10", "scope": "merchant", "kind": "random_event_xyz", "source": "external",
            "merchant_id": "ct_m10", "customer_id": None,
            "payload": {"info": "something unexpected"},
            "urgency": 2, "suppression_key": "ct_test_10", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 11. minimal data merchant
    {
        "name": "Minimal Data Merchant",
        "merchant": {
            "merchant_id": "ct_m11", "category_slug": "salons",
            "identity": {"name": "New Salon", "owner_first_name": "", "city": "", "locality": "", "verified": False, "languages": ["en"]},
            "subscription": {"status": "active", "plan": "Basic", "days_remaining": 30},
            "performance": {"window_days": 30, "views": 0, "calls": 0, "directions": 0, "ctr": 0, "leads": 0, "delta_7d": {}},
            "offers": [], "customer_aggregate": {}, "signals": [], "conversation_history": [],
        },
        "trigger": {
            "id": "ct_trg11", "scope": "merchant", "kind": "perf_dip", "source": "internal",
            "merchant_id": "ct_m11", "customer_id": None,
            "payload": {"metric": "views", "delta_pct": -0.30, "window": "7d"},
            "urgency": 3, "suppression_key": "ct_test_11", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
    # 12. competitor_opened — dentist
    {
        "name": "Competitor Opened — Dentist",
        "merchant": make_merchant("ct_m12", "dentists", "Dr. Patel Dental", "Patel", "Delhi", "Dwarka",
                                  views=1800, calls=15),
        "trigger": {
            "id": "ct_trg12", "scope": "merchant", "kind": "competitor_opened", "source": "external",
            "merchant_id": "ct_m12", "customer_id": None,
            "payload": {"competitor_name": "BrightSmile Clinic", "distance_km": 0.8, "their_offer": "Free Consultation + X-Ray"},
            "urgency": 2, "suppression_key": "ct_test_12", "expires_at": "2026-12-31T00:00:00Z",
        },
    },
]

# ═══════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════

def push_context(scope, cid, payload):
    """Push a single context; return True on success."""
    try:
        r = requests.post(f"{BASE_URL}/v1/context", json={
            "scope": scope, "context_id": cid, "version": VERSION,
            "payload": payload, "delivered_at": datetime.now(timezone.utc).isoformat(),
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"    [ERR] push {scope}/{cid}: {e}")
        return False


def _stamp(d: dict, id_key: str, extra_keys: list[str] = None) -> dict:
    """Deep-copy dict and append RUN_ID to the id field + any extra keys."""
    d = copy.deepcopy(d)
    if id_key in d:
        d[id_key] = f"{d[id_key]}_{RUN_ID}"
    for k in (extra_keys or []):
        if k in d and d[k]:
            d[k] = f"{d[k]}_{RUN_ID}"
    return d


def run_single_test(idx, tc):
    """Push contexts for one test case, call tick, display results."""
    name = tc["name"]

    # Stamp unique IDs for this run to avoid suppression/cooldown collisions
    merchant = _stamp(tc["merchant"], "merchant_id")
    trigger = _stamp(tc["trigger"], "id", ["merchant_id", "customer_id", "suppression_key"])
    customer = _stamp(tc["customer"], "customer_id", ["merchant_id"]) if tc.get("customer") else None

    mid = merchant["merchant_id"]
    tid = trigger["id"]
    cat_slug = merchant["category_slug"]

    print(f"\n{'='*60}")
    print(f"  Test {idx}: {name}")
    print(f"{'='*60}")

    # Push category
    cat = CATEGORIES.get(cat_slug, CATEGORIES["restaurants"])
    if not push_context("category", cat_slug, cat):
        print("  [WARN] Category push issue (may already exist)")

    # Push merchant
    if not push_context("merchant", mid, merchant):
        print("  [WARN] Merchant push issue")

    # Push customer (if present)
    if customer:
        cid = customer["customer_id"]
        if not push_context("customer", cid, customer):
            print("  [WARN] Customer push issue")

    # Push trigger
    if not push_context("trigger", tid, trigger):
        print("  [WARN] Trigger push issue")

    # Call tick
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        r = requests.post(f"{BASE_URL}/v1/tick", json={
            "now": now_iso, "available_triggers": [tid],
        }, timeout=15)

        print(f"  Status:  {r.status_code}")

        if r.status_code == 200:
            data = r.json()
            actions = data.get("actions", [])

            if actions:
                a = actions[0]
                body = a.get("body", "")
                print(f"  Body:    {body[:200]}{'...' if len(body) > 200 else ''}")
                print(f"  CTA:     {a.get('cta', '-')}")
                print(f"  Send As: {a.get('send_as', '-')}")
                rationale = a.get("rationale", "-")
                print(f"  Ration.: {rationale[:150]}{'...' if len(str(rationale)) > 150 else ''}")
                print(f"  Result:  [PASS] Action generated")
            else:
                print(f"  Result:  [SKIP] No action returned (suppressed/filtered)")
        else:
            print(f"  Error:   {r.text[:200]}")

    except Exception as e:
        print(f"  Exception: {e}")


def main():
    print("\n" + ">>>  VERA AI -- CUSTOM TEST RUNNER  <<<")
    print(f"Target: {BASE_URL}\n")

    # Quick health check
    try:
        r = requests.get(f"{BASE_URL}/v1/healthz", timeout=5)
        if r.status_code == 200:
            print(f"[✅] Server is up: {r.json()}")
        else:
            print(f"[❌] Server returned {r.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"[❌] Cannot reach server: {e}")
        sys.exit(1)

    passed = 0
    failed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        run_single_test(i, tc)
        time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"  Done — {len(TEST_CASES)} test cases executed.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
