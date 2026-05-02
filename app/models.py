"""
Vera AI Challenge — Pydantic Models
Defines all request/response schemas for the 5 API endpoints.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Optional


# ─── /v1/context ────────────────────────────────────────────

class ContextPushRequest(BaseModel):
    scope: str  # "category" | "merchant" | "customer" | "trigger"
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str


class ContextPushResponse(BaseModel):
    accepted: bool
    ack_id: str | None = None
    stored_at: str | None = None
    reason: str | None = None
    current_version: int | None = None
    details: str | None = None


# ─── /v1/tick ───────────────────────────────────────────────

class TickRequest(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class TickAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: str | None = None
    send_as: str  # "vera" | "merchant_on_behalf"
    trigger_id: str
    template_name: str
    template_params: list[str] = Field(default_factory=list)
    body: str
    cta: str  # "binary_yes_no" | "open_ended" | "multi_choice_slot" | "none" | ...
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: list[TickAction] = Field(default_factory=list)


# ─── /v1/reply ──────────────────────────────────────────────

class ReplyRequest(BaseModel):
    conversation_id: str
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str  # "merchant" | "customer"
    message: str
    received_at: str
    turn_number: int


class ReplyResponse(BaseModel):
    action: str  # "send" | "wait" | "end"
    body: str | None = None
    cta: str | None = None
    wait_seconds: int | None = None
    rationale: str


# ─── /v1/healthz ────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    uptime_seconds: int
    contexts_loaded: dict[str, int]


# ─── /v1/metadata ───────────────────────────────────────────

class MetadataResponse(BaseModel):
    team_name: str
    team_members: list[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str
