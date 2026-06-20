"""Request/response schemas for publication moderation and verification (R11).

The moderation router exposes platform-only actions that either change a Job's
publication ``status`` (block/unpublish) or drive a verifiable entity's
``verification_status`` through the state machine (mark_review/verify). The
shared response surface reports the affected entity's identity plus its current
publication and verification states so callers can confirm the outcome.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModerationActionRequest(BaseModel):
    """Optional context for a moderation action.

    ``reason`` is recorded on the audit entry (and, for state-machine
    transitions, in the transition's ``after`` snapshot) for traceability.
    """

    reason: str | None = Field(default=None, max_length=1024)


class JobModerationResponse(BaseModel):
    """Outcome of a job moderation action (block/unpublish/mark_review/verify)."""

    id: str
    status: str
    verification_status: str


class EntityVerificationResponse(BaseModel):
    """Outcome of a company/profile verification action."""

    id: str
    verification_status: str
