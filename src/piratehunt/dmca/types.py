from __future__ import annotations

from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from pydantic import BaseModel, Field


class TakedownStatus(str, PyEnum):
    """Lifecycle states for DMCA takedown cases."""

    drafted = "drafted"
    pending_review = "pending_review"
    submitted = "submitted"
    acknowledged = "acknowledged"
    taken_down = "taken_down"
    expired = "expired"
    rejected = "rejected"


class DraftNotice(BaseModel):
    """Generated DMCA draft notice ready for review or submission."""

    platform: str = Field(..., description="Target platform (youtube, telegram, etc.)")
    recipient_email_or_form_url: str = Field(
        ..., description="Email address or form URL for platform abuse team"
    )
    subject: str = Field(..., description="Notice subject line")
    body: str = Field(..., description="Full notice body text")
    language: str = Field(
        default="en", description="Language code (en, ru, hi, etc.)"
    )
    gemini_polish_applied: bool = Field(
        default=False, description="Whether Gemini polishing was successfully applied"
    )
    evidence_uris: list[str] = Field(
        default_factory=list, description="List of evidence artifact URIs"
    )
    fingerprint_match_scores: dict[str, float] = Field(
        default_factory=dict, description="Audio/visual match scores"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RightsHolderInfo(BaseModel):
    """Information about a copyright rights holder."""

    id: str = Field(..., description="Unique identifier (UUID)")
    name: str = Field(..., description="Legal name of rights holder")
    legal_email: str = Field(..., description="Official contact email")
    address: str = Field(..., description="Legal address")
    authorized_agent: str = Field(..., description="Name/title of authorized agent")
    default_language: str = Field(default="en", description="Default language for notices")
    signature_block: str = Field(..., description="Legal signature block for notices")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TakedownCaseInfo(BaseModel):
    """Takedown case with full history and metadata."""

    id: str = Field(..., description="Case UUID")
    verification_result_id: str = Field(..., description="Verification result UUID")
    candidate_id: str = Field(..., description="Candidate stream UUID")
    match_id: str = Field(..., description="Original match UUID")
    platform: str = Field(..., description="Target platform")
    status: TakedownStatus = Field(..., description="Current case status")
    draft_subject: str = Field(..., description="Notice subject")
    draft_body: str = Field(..., description="Notice body")
    draft_language: str = Field(default="en", description="Notice language")
    recipient: str = Field(..., description="Recipient email or URL")
    gemini_polish_applied: bool = Field(default=False)
    drafted_at: datetime = Field(..., description="When notice was drafted")
    last_status_at: datetime = Field(..., description="Last status transition time")
    submitted_at: Optional[datetime] = Field(None, description="When submitted to platform")
    resolved_at: Optional[datetime] = Field(None, description="When case resolved")
    notes: Optional[str] = Field(None, description="Internal notes")
    events: list[TakedownEventInfo] = Field(
        default_factory=list, description="Event history"
    )


class TakedownEventInfo(BaseModel):
    """Event record for takedown case audit trail."""

    id: str = Field(..., description="Event UUID")
    case_id: str = Field(..., description="Associated case UUID")
    from_status: TakedownStatus = Field(..., description="Previous status")
    to_status: TakedownStatus = Field(..., description="New status")
    actor: str = Field(..., description="Actor (system or user:<id>)")
    payload: dict = Field(default_factory=dict, description="Event metadata (JSONB)")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InvalidTransitionError(Exception):
    """Raised when an invalid status transition is attempted."""

    def __init__(self, from_status: TakedownStatus, to_status: TakedownStatus):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Invalid transition from {from_status} to {to_status}"
        )


# Valid state transitions
VALID_TRANSITIONS = {
    TakedownStatus.drafted: [
        TakedownStatus.pending_review,
        TakedownStatus.rejected,
    ],
    TakedownStatus.pending_review: [
        TakedownStatus.submitted,
        TakedownStatus.rejected,
    ],
    TakedownStatus.submitted: [
        TakedownStatus.acknowledged,
        TakedownStatus.expired,
        TakedownStatus.rejected,
    ],
    TakedownStatus.acknowledged: [
        TakedownStatus.taken_down,
        TakedownStatus.rejected,
    ],
    TakedownStatus.taken_down: [],  # Terminal state
    TakedownStatus.expired: [],  # Terminal state
    TakedownStatus.rejected: [],  # Terminal state
}
