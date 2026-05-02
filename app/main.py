"""
Vera AI Challenge — Main FastAPI Application
Implements all 5 endpoints: healthz, metadata, context, tick, reply.
"""

from __future__ import annotations
import time, logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.config import TEAM_NAME, TEAM_MEMBERS, CONTACT_EMAIL, BOT_VERSION
from app.models import (
    ContextPushRequest, ContextPushResponse,
    TickRequest, TickResponse, TickAction,
    ReplyRequest, ReplyResponse,
    HealthResponse, MetadataResponse,
)
from app.context_store import ContextStore
from app.trigger_dispatcher import dispatch_tick
from app.reply_handler import ReplyHandler
from app.fact_extractor import extract_facts
from app.message_generator import generate_reply_body

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vera")

# ── App + global state ───────────────────────────────────────
app = FastAPI(title="Vera AI Challenge Bot", version=BOT_VERSION)
START_TIME = time.time()
store = ContextStore()
reply_handler = ReplyHandler()


# ═════════════════════════════════════════════════════════════
# GET /v1/healthz
# ═════════════════════════════════════════════════════════════

@app.get("/v1/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": store.counts(),
    }


# ═════════════════════════════════════════════════════════════
# GET /v1/metadata
# ═════════════════════════════════════════════════════════════

@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": TEAM_NAME,
        "team_members": TEAM_MEMBERS,
        "model": "deterministic-template-engine",
        "approach": "Fully deterministic decision engine + rule-based CTA + template-based message generator",
        "contact_email": CONTACT_EMAIL,
        "version": BOT_VERSION,
        "submitted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ═════════════════════════════════════════════════════════════
# POST /v1/context
# ═════════════════════════════════════════════════════════════

VALID_SCOPES = {"category", "merchant", "customer", "trigger"}

@app.post("/v1/context")
async def push_context(body: ContextPushRequest):
    # Validate scope
    if body.scope not in VALID_SCOPES:
        return JSONResponse(
            status_code=400,
            content={"accepted": False, "reason": "invalid_scope", "details": f"Scope must be one of {VALID_SCOPES}"},
        )

    accepted, current_version = store.upsert(body.scope, body.context_id, body.version, body.payload)

    if not accepted:
        return JSONResponse(
            status_code=409,
            content={"accepted": False, "reason": "stale_version", "current_version": current_version},
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(time.time()*1000)%1000:03d}Z"
    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": now,
    }


# ═════════════════════════════════════════════════════════════
# POST /v1/tick
# ═════════════════════════════════════════════════════════════

@app.post("/v1/tick")
async def tick(body: TickRequest):
    try:
        actions = dispatch_tick(store, body.available_triggers, body.now)
        return {"actions": actions}
    except Exception as e:
        logger.error(f"Tick error: {e}", exc_info=True)
        # Return empty actions on error — never timeout
        return {"actions": []}


# ═════════════════════════════════════════════════════════════
# POST /v1/reply
# ═════════════════════════════════════════════════════════════

@app.post("/v1/reply")
async def reply(body: ReplyRequest):
    try:
        # Check if conversation was already ended
        if store.is_conversation_ended(body.conversation_id):
            return {
                "action": "end",
                "rationale": "Conversation was previously ended.",
            }

        # Classify the reply using rule-first handler
        result = reply_handler.classify(body.conversation_id, body.merchant_id, body.message, body.turn_number)
        action = result.get("action", "end")

        # If action is "end", record it
        if action == "end":
            store.end_conversation(body.conversation_id)
            return {
                "action": "end",
                "rationale": result.get("rationale", "Conversation ended."),
            }

        # If action is "wait", return wait_seconds
        if action == "wait":
            return {
                "action": "wait",
                "wait_seconds": result.get("wait_seconds", 3600),
                "rationale": result.get("rationale", "Waiting before retry."),
            }

        # If action is "send", we need to generate a reply body
        if action == "send":
            reply_body = result.get("body")

            # If body is None, generate via LLM
            if reply_body is None:
                merchant_id = body.merchant_id or ""
                merchant = store.get_merchant(merchant_id) or {}
                category = store.get_merchant_category(merchant) or {}
                customer = store.get_customer(body.customer_id) if body.customer_id else None

                # Build a minimal trigger for fact extraction
                dummy_trigger = {"kind": "reply", "scope": "merchant", "source": "internal",
                                 "payload": {}, "urgency": 3, "merchant_id": merchant_id}
                facts = extract_facts(category, merchant, dummy_trigger, customer)

                intent = result.get("intent", "general")
                history = reply_handler.get_conversation_history(body.conversation_id)

                reply_body = generate_reply_body(
                    facts=facts,
                    category=category,
                    merchant_message=body.message,
                    intent=intent,
                    conversation_history=history,
                )

            cta = result.get("cta", "open_ended")
            rationale = result.get("rationale", "Continuing conversation.")

            return {
                "action": "send",
                "body": reply_body,
                "cta": cta,
                "rationale": rationale,
            }

        # Fallback
        return {
            "action": "end",
            "rationale": "Unhandled reply state; closing safely.",
        }

    except Exception as e:
        logger.error(f"Reply error: {e}", exc_info=True)
        return {
            "action": "wait",
            "wait_seconds": 3600,
            "rationale": f"Internal error — backing off. Error: {str(e)[:100]}",
        }


# ═════════════════════════════════════════════════════════════
# Root redirect
# ═════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"message": "Vera AI Challenge Bot is running. Use /v1/healthz to check status."}
