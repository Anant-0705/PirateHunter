"""Dashboard event types for WebSocket streaming."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of dashboard events."""

    ingestion_started = "ingestion_started"
    ingestion_completed = "ingestion_completed"
    candidate_discovered = "candidate_discovered"
    verification_started = "verification_started"
    pirate_confirmed = "pirate_confirmed"
    clean_confirmed = "clean_confirmed"
    takedown_drafted = "takedown_drafted"
    takedown_status_changed = "takedown_status_changed"


class GeoLocation(BaseModel):
    """Geographic location."""

    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")
    country: str = Field(..., description="ISO 3166-1 alpha-2 country code")
    country_name: str = Field(..., description="Country name")
    city: str | None = Field(None, description="City name if known")


class IngestionStarted(BaseModel):
    """Ingestion of a match has started."""

    type: Literal["ingestion_started"] = "ingestion_started"
    match_id: str = Field(..., description="Match UUID")
    match_name: str = Field(..., description="Match name")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class IngestionCompleted(BaseModel):
    """Ingestion of a match has completed."""

    type: Literal["ingestion_completed"] = "ingestion_completed"
    match_id: str = Field(..., description="Match UUID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CandidateDiscovered(BaseModel):
    """A pirate candidate stream was discovered."""

    type: Literal["candidate_discovered"] = "candidate_discovered"
    match_id: str = Field(..., description="Match UUID")
    candidate_id: str = Field(..., description="Candidate UUID")
    platform: str = Field(..., description="Source platform (youtube, telegram, etc.)")
    url: str = Field(..., description="Source URL")
    location: GeoLocation = Field(..., description="Geocoded location of URL host")
    confidence_hint: float = Field(..., description="Initial confidence 0-1")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VerificationStarted(BaseModel):
    """Verification of a candidate has started."""

    type: Literal["verification_started"] = "verification_started"
    match_id: str = Field(..., description="Match UUID")
    candidate_id: str = Field(..., description="Candidate UUID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PirateConfirmed(BaseModel):
    """A candidate was verified as a pirate."""

    type: Literal["pirate_confirmed"] = "pirate_confirmed"
    match_id: str = Field(..., description="Match UUID")
    candidate_id: str = Field(..., description="Candidate UUID")
    verification_result_id: str = Field(..., description="Verification result UUID")
    platform: str = Field(..., description="Source platform")
    url: str = Field(..., description="Source URL")
    location: GeoLocation = Field(..., description="Geocoded location")
    audio_score: float = Field(..., description="Audio fingerprint match 0-1")
    visual_score: float = Field(..., description="Visual fingerprint match 0-1")
    combined_score: float = Field(..., description="Combined score 0-1")
    gemini_verdict: str = Field(..., description="Gemini Vision verdict")
    detection_latency_ms: float = Field(
        ..., description="Time from discovery to confirmation (ms)"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CleanConfirmed(BaseModel):
    """A candidate was verified as clean."""

    type: Literal["clean_confirmed"] = "clean_confirmed"
    match_id: str = Field(..., description="Match UUID")
    candidate_id: str = Field(..., description="Candidate UUID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TakedownDrafted(BaseModel):
    """A DMCA takedown notice was drafted."""

    type: Literal["takedown_drafted"] = "takedown_drafted"
    match_id: str = Field(..., description="Match UUID")
    case_id: str = Field(..., description="Takedown case UUID")
    platform: str = Field(..., description="Target platform")
    gemini_polish_applied: bool = Field(..., description="Whether Gemini polished the notice")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TakedownStatusChanged(BaseModel):
    """A takedown case transitioned to a new status."""

    type: Literal["takedown_status_changed"] = "takedown_status_changed"
    match_id: str = Field(..., description="Match UUID")
    case_id: str = Field(..., description="Takedown case UUID")
    from_status: str = Field(..., description="Previous status")
    to_status: str = Field(..., description="New status")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Discriminated union of all dashboard events
DashboardEvent = (
    IngestionStarted
    | IngestionCompleted
    | CandidateDiscovered
    | VerificationStarted
    | PirateConfirmed
    | CleanConfirmed
    | TakedownDrafted
    | TakedownStatusChanged
)


class DashboardSummary(BaseModel):
    """Summary statistics for a match dashboard."""

    match_id: str = Field(..., description="Match UUID")
    active_pirates: int = Field(..., description="Currently unresolved pirate streams")
    total_detected: int = Field(..., description="Total pirate candidates discovered")
    total_drafted: int = Field(..., description="DMCA notices drafted")
    total_submitted: int = Field(..., description="Notices submitted to platforms")
    total_taken_down: int = Field(..., description="Streams confirmed taken down")
    est_revenue_loss_inr: float = Field(
        ..., description="Estimated revenue loss in Indian Rupees"
    )
    avg_detection_latency_ms: float = Field(..., description="Average detection latency (ms)")
    top_platforms: list[dict[str, Any]] = Field(..., description="Top platforms by count")


class PirateEntry(BaseModel):
    """Active pirate stream with location for globe rendering."""

    candidate_id: str = Field(..., description="Candidate UUID")
    platform: str = Field(..., description="Source platform")
    url: str = Field(..., description="Source URL")
    confidence: float = Field(..., description="Combined confidence score 0-1")
    location: GeoLocation = Field(..., description="Geocoded location")
    discovered_at: datetime = Field(..., description="When discovered")
    last_seen: datetime = Field(..., description="Last activity time")
    status: Literal["active", "draft", "submitted"] = Field(..., description="Current status")


class TakedownFunnelData(BaseModel):
    """Funnel data for takedown lifecycle."""

    detected: int = Field(..., description="Pirates detected")
    verified: int = Field(..., description="Verified as pirate")
    drafted: int = Field(..., description="DMCA drafted")
    submitted: int = Field(..., description="Submitted to platform")
    taken_down: int = Field(..., description="Confirmed taken down")


class TimelineEvent(BaseModel):
    """Bucketed event count for timeline chart."""

    timestamp: datetime = Field(..., description="Bucket start time")
    detections: int = Field(..., description="Pirates detected in this bucket")
    takedowns: int = Field(..., description="Streams taken down in this bucket")
