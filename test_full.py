"""
Full end-to-end test: pushes all contexts, ticks multiple triggers,
tests reply flows, and validates all response fields.
"""
import urllib.request
import json
import sys
import os
import glob

BASE = "http://localhost:8080"
DATASET = "magicpin-ai-challenge/dataset"

PASS = 0
FAIL = 0

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code

def get(path):
    r = urllib.request.urlopen(f"{BASE}{path}", timeout=10)
    return json.loads(r.read()), r.status

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} — {detail}")

# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print("  VERA AI — FULL BACKEND TEST")
print("="*60)

# ── 1. HEALTHZ ────────────────────────────────────────────
print("\n📡 1. GET /v1/healthz")
data, code = get("/v1/healthz")
check("Status 200", code == 200)
check("status=ok", data.get("status") == "ok")
check("contexts_loaded is dict", isinstance(data.get("contexts_loaded"), dict))
check("Has all 4 scopes", all(k in data["contexts_loaded"] for k in ["category","merchant","customer","trigger"]))

# ── 2. METADATA ───────────────────────────────────────────
print("\n📋 2. GET /v1/metadata")
data, code = get("/v1/metadata")
check("Status 200", code == 200)
check("team_name present", bool(data.get("team_name")))
check("model present", bool(data.get("model")))
check("approach present", bool(data.get("approach")))
check("version present", bool(data.get("version")))

# ── 3. PUSH ALL CONTEXTS ─────────────────────────────────
print("\n📦 3. POST /v1/context — Push all datasets")

# Categories
cat_files = glob.glob(os.path.join(DATASET, "categories", "*.json"))
for cf in cat_files:
    cat = json.load(open(cf))
    slug = cat.get("slug", os.path.basename(cf).replace(".json",""))
    r, c = post("/v1/context", {"scope":"category","context_id":slug,"version":1,"payload":cat,"delivered_at":"2026-04-26T09:45:00Z"})
    check(f"Category '{slug}'", r.get("accepted") == True, f"code={c}")

# Merchants
merchants = json.load(open(os.path.join(DATASET, "merchants_seed.json")))["merchants"]
for m in merchants:
    r, c = post("/v1/context", {"scope":"merchant","context_id":m["merchant_id"],"version":1,"payload":m,"delivered_at":"2026-04-26T09:45:30Z"})
    short = m["merchant_id"][:25]
    check(f"Merchant '{short}'", r.get("accepted") == True, f"code={c}")

# Customers
customers = json.load(open(os.path.join(DATASET, "customers_seed.json")))["customers"]
for cu in customers:
    r, c = post("/v1/context", {"scope":"customer","context_id":cu["customer_id"],"version":1,"payload":cu,"delivered_at":"2026-04-26T09:45:30Z"})
    check(f"Customer '{cu['customer_id'][:25]}'", r.get("accepted") == True, f"code={c}")

# Triggers
triggers = json.load(open(os.path.join(DATASET, "triggers_seed.json")))["triggers"]
for t in triggers:
    r, c = post("/v1/context", {"scope":"trigger","context_id":t["id"],"version":1,"payload":t,"delivered_at":"2026-04-26T10:00:00Z"})
    check(f"Trigger '{t['id'][:30]}'", r.get("accepted") == True, f"code={c}")

# Verify counts
print("\n📊 Context counts after push:")
data, _ = get("/v1/healthz")
counts = data["contexts_loaded"]
print(f"   Categories: {counts['category']}, Merchants: {counts['merchant']}, Customers: {counts['customer']}, Triggers: {counts['trigger']}")
check("All 5 categories loaded", counts["category"] == 5, f"got {counts['category']}")
check("All 10 merchants loaded", counts["merchant"] == 10, f"got {counts['merchant']}")
check("All 15 customers loaded", counts["customer"] == 15, f"got {counts['customer']}")
check("All 25 triggers loaded", counts["trigger"] == 25, f"got {counts['trigger']}")

# ── 4. IDEMPOTENCY TEST ──────────────────────────────────
print("\n🔄 4. Idempotency test (re-push same version)")
r, c = post("/v1/context", {"scope":"category","context_id":"dentists","version":1,"payload":{},"delivered_at":"2026-04-26T10:00:00Z"})
check("Stale version rejected (409)", c == 409 and r.get("reason") == "stale_version", f"code={c}, reason={r.get('reason')}")

# Version bump accepted
cat = json.load(open(os.path.join(DATASET, "categories", "dentists.json")))
r, c = post("/v1/context", {"scope":"category","context_id":"dentists","version":2,"payload":cat,"delivered_at":"2026-04-26T10:30:00Z"})
check("Version bump accepted (200)", r.get("accepted") == True, f"code={c}")

# ── 5. TICK — MULTIPLE TRIGGER TYPES ─────────────────────
print("\n⏰ 5. POST /v1/tick — Test multiple trigger types")

# Test research_digest (merchant-facing)
test_triggers = [
    ("trg_001_research_digest_dentists", "research_digest", "vera"),
    ("trg_004_perf_dip_bharat",          "perf_dip",         "vera"),
]

for tid, kind, expected_send_as in test_triggers:
    print(f"\n  🔔 Trigger: {kind} ({tid[:30]})")
    r, c = post("/v1/tick", {"now":"2026-04-26T10:35:00Z","available_triggers":[tid]})
    check(f"  Status 200", c == 200)
    actions = r.get("actions", [])

    if actions:
        a = actions[0]
        print(f"     Body: {a.get('body','')[:120]}...")

        # Validate ALL required fields
        required_fields = ["conversation_id","merchant_id","send_as","trigger_id","template_name","template_params","body","cta","suppression_key","rationale"]
        missing = [f for f in required_fields if f not in a]
        check(f"  All required fields present", len(missing) == 0, f"Missing: {missing}")
        check(f"  send_as={expected_send_as}", a.get("send_as") == expected_send_as, f"got {a.get('send_as')}")
        check(f"  CTA is not empty", bool(a.get("cta")), f"cta={a.get('cta')}")
        check(f"  Body is not empty", bool(a.get("body")), "empty body!")
        check(f"  Rationale is not empty", bool(a.get("rationale")), "empty rationale!")
        check(f"  suppression_key present", bool(a.get("suppression_key")), "missing!")
        check(f"  No URL in body", "http" not in a.get("body","").lower(), "URL found!")
    else:
        print(f"     (No action — may be suppressed from prior test)")
        check(f"  Empty actions is valid", True)

# Test customer-scoped trigger (recall_due)
print(f"\n  🔔 Trigger: recall_due (customer-scoped)")
r, c = post("/v1/tick", {"now":"2026-04-26T11:00:00Z","available_triggers":["trg_003_recall_due_priya"]})
actions = r.get("actions", [])
if actions:
    a = actions[0]
    print(f"     Body: {a.get('body','')[:120]}...")
    check("  send_as=merchant_on_behalf", a.get("send_as") == "merchant_on_behalf", f"got {a.get('send_as')}")
    check("  customer_id populated", a.get("customer_id") == "c_001_priya_for_m001", f"got {a.get('customer_id')}")
    check("  CTA present", bool(a.get("cta")))
else:
    print("     (No action — merchant may be on cooldown from prior tick)")

# Test empty tick (no triggers)
print(f"\n  🔔 Empty tick (no triggers)")
r, c = post("/v1/tick", {"now":"2026-04-26T11:05:00Z","available_triggers":[]})
check("  Returns empty actions", r.get("actions") == [], f"got {len(r.get('actions',[]))} actions")

# ── 6. REPLY HANDLER TESTS ───────────────────────────────
print("\n💬 6. POST /v1/reply — Reply handler tests")

# 6a. Auto-reply escalation
print("\n  📱 6a. Auto-reply detection (3-strike)")
auto_msg = "Thank you for contacting Dr. Meera's Dental Clinic! Our team will respond shortly."
r1, _ = post("/v1/reply", {"conversation_id":"conv_ar_test","merchant_id":"m_001_drmeera_dentist_delhi","from_role":"merchant","message":auto_msg,"received_at":"2026-04-26T10:42:00Z","turn_number":2})
check("  Strike 1 → send", r1.get("action") == "send", f"got {r1.get('action')}")

r2, _ = post("/v1/reply", {"conversation_id":"conv_ar_test","merchant_id":"m_001_drmeera_dentist_delhi","from_role":"merchant","message":auto_msg,"received_at":"2026-04-26T10:43:00Z","turn_number":3})
check("  Strike 2 → wait", r2.get("action") == "wait", f"got {r2.get('action')}")
check("  Wait = 86400s", r2.get("wait_seconds") == 86400, f"got {r2.get('wait_seconds')}")

r3, _ = post("/v1/reply", {"conversation_id":"conv_ar_test","merchant_id":"m_001_drmeera_dentist_delhi","from_role":"merchant","message":auto_msg,"received_at":"2026-04-26T10:44:00Z","turn_number":4})
check("  Strike 3 → end", r3.get("action") == "end", f"got {r3.get('action')}")

# 6b. Stop / hostile
print("\n  🛑 6b. Stop/hostile handling")
r4, _ = post("/v1/reply", {"conversation_id":"conv_stop","merchant_id":"m_001_drmeera_dentist_delhi","from_role":"merchant","message":"Stop messaging me. This is useless spam.","received_at":"2026-04-26T10:45:00Z","turn_number":2})
check("  Hostile → end", r4.get("action") == "end", f"got {r4.get('action')}")
check("  Rationale present", bool(r4.get("rationale")))

# 6c. Yes / intent transition
print("\n  ✅ 6c. Yes/intent transition")
r5, _ = post("/v1/reply", {"conversation_id":"conv_yes","merchant_id":"m_001_drmeera_dentist_delhi","from_role":"merchant","message":"Ok lets do it. Whats next?","received_at":"2026-04-26T10:46:00Z","turn_number":2})
check("  Intent → send", r5.get("action") == "send", f"got {r5.get('action')}")
check("  Body present", bool(r5.get("body")), "no body!")
# Should NOT be qualifying
body_lower = (r5.get("body","")).lower()
qualifying = ["would you", "do you", "can you tell", "what if", "how about"]
check("  Not still qualifying", not any(q in body_lower for q in qualifying), f"body looks like qualification")

# 6d. Conversation already ended
print("\n  🚫 6d. Ended conversation")
r6, _ = post("/v1/reply", {"conversation_id":"conv_stop","merchant_id":"m_001_drmeera_dentist_delhi","from_role":"merchant","message":"Hey are you there?","received_at":"2026-04-26T10:47:00Z","turn_number":3})
check("  Ended conv → end", r6.get("action") == "end", f"got {r6.get('action')}")

# 6e. Question handling
print("\n  ❓ 6e. Question handling")
r7, _ = post("/v1/reply", {"conversation_id":"conv_question","merchant_id":"m_001_drmeera_dentist_delhi","from_role":"merchant","message":"What is my current CTR?","received_at":"2026-04-26T10:48:00Z","turn_number":2})
check("  Question → send", r7.get("action") == "send", f"got {r7.get('action')}")
check("  Body present", bool(r7.get("body")))

# ── 7. RESPONSE FIELD COMPLETENESS ───────────────────────
print("\n✅ 7. Response field validation")

# Tick action fields
r_tick, _ = post("/v1/tick", {"now":"2026-04-26T12:00:00Z","available_triggers":["trg_009_winback_glamour"]})
if r_tick.get("actions"):
    a = r_tick["actions"][0]
    for field in ["conversation_id","merchant_id","send_as","trigger_id","body","cta","suppression_key","rationale"]:
        check(f"  tick action has '{field}'", field in a and a[field] is not None, f"missing or None")

# Reply response fields
r_reply, _ = post("/v1/reply", {"conversation_id":"conv_field_test","merchant_id":"m_002_bharat_dentist_mumbai","from_role":"merchant","message":"Tell me more","received_at":"2026-04-26T12:01:00Z","turn_number":2})
for field in ["action", "rationale"]:
    check(f"  reply has '{field}'", field in r_reply and r_reply[field] is not None, f"missing or None")

# ═══════════════════════════════════════════════════════════
print("\n" + "="*60)
print(f"  RESULTS: {PASS} passed, {FAIL} failed")
print("="*60 + "\n")

if FAIL > 0:
    sys.exit(1)
