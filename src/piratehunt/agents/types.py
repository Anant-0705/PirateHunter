from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DiscoveryQuery(BaseModel):
    """Input contract shared by all discovery agents."""

    match_id: UUID
    keywords: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["en"])
    started_at: datetime = Field(default_factory=datetime.utcnow)
    match_clock_seconds: int = Field(default=0, ge=0)
    region_hints: list[str] = Field(default_factory=list)


class CandidateStream(BaseModel):
    """Candidate stream found by a discovery agent."""

    id: UUID = Field(default_factory=uuid4)
    match_id: UUID
    source_platform: str
    source_url: str
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    discovered_by_agent: str
    metadata: dict[str, object] = Field(default_factory=dict)
    confidence_hint: float = Field(ge=0.0, le=1.0)


class AgentHealth(BaseModel):
    """Health details for one discovery agent."""

    healthy: bool
    last_run: datetime
    error: str | None = None
