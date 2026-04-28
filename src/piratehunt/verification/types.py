from __future__ import annotations

from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field


class SampledClip(BaseModel):
    """A short downloaded clip used for candidate verification."""

    path: Path
    duration: float
    source_format: str
    sampler_used: str


class GeminiVerificationSignal(BaseModel):
    """Secondary visual signal from Gemini Vision."""

    is_sports_content: bool
    detected_sport: str | None = None
    broadcaster_logos_detected: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    raw_response: str


class EvidenceArtifact(BaseModel):
    """Evidence storage result."""

    artifact_id: str
    storage_uris: dict[str, str]


class CandidateVerified(BaseModel):
    """Redis event emitted after verification completes."""

    candidate_id: UUID
    match_id: UUID
    verdict: str
    combined_score: float
    verification_id: UUID


class PirateConfirmed(BaseModel):
    """Redis event emitted for confirmed pirate streams."""

    candidate_id: UUID
    match_id: UUID
    source_url: str
    combined_score: float
    verification_id: UUID
    evidence_artifact_id: str | None = None
