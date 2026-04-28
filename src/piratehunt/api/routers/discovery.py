from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.agents.types import DiscoveryQuery
from piratehunt.api.dependencies import get_session
from piratehunt.db.models import AgentRun, CandidateStatus, CandidateStream
from piratehunt.db.repository import (
    get_match,
    list_candidates,
    list_recent_agent_runs,
)

router = APIRouter(tags=["discovery"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class StartDiscoveryRequest(BaseModel):
    """Request body for starting discovery."""

    keywords: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["en"])
    region_hints: list[str] = Field(default_factory=list)
    match_clock_seconds: int = Field(default=0, ge=0)


class StartDiscoveryResponse(BaseModel):
    """Response after a discovery run is started."""

    discovery_run_id: uuid.UUID


class CandidateResponse(BaseModel):
    """Candidate stream response."""

    id: uuid.UUID
    match_id: uuid.UUID
    source_platform: str
    source_url: str
    discovered_at: str
    discovered_by_agent: str
    metadata: dict[str, object]
    confidence_hint: float
    status: CandidateStatus
    verified_at: str | None
    notes: str | None


class AgentRunResponse(BaseModel):
    """Agent run response for health endpoints."""

    id: uuid.UUID
    match_id: uuid.UUID
    agent_name: str
    started_at: str
    finished_at: str | None
    status: str
    candidates_found: int
    error: str | None


def _serialize_candidate(candidate: CandidateStream) -> CandidateResponse:
    return CandidateResponse(
        id=candidate.id,
        match_id=candidate.match_id,
        source_platform=candidate.source_platform,
        source_url=candidate.source_url,
        discovered_at=candidate.discovered_at.isoformat(),
        discovered_by_agent=candidate.discovered_by_agent,
        metadata=candidate.candidate_metadata,
        confidence_hint=candidate.confidence_hint,
        status=candidate.status,
        verified_at=candidate.verified_at.isoformat() if candidate.verified_at else None,
        notes=candidate.notes,
    )


def _serialize_agent_run(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=run.id,
        match_id=run.match_id,
        agent_name=run.agent_name,
        started_at=run.started_at.isoformat(),
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        status=run.status.value,
        candidates_found=run.candidates_found,
        error=run.error,
    )


@router.post(
    "/matches/{match_id}/discover",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StartDiscoveryResponse,
)
async def start_discovery_endpoint(
    match_id: uuid.UUID,
    payload: StartDiscoveryRequest,
    request: Request,
    session: SessionDep,
) -> StartDiscoveryResponse:
    """Start discovery agents for a match."""
    match = await get_match(session, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    query = DiscoveryQuery(
        match_id=match_id,
        keywords=payload.keywords,
        languages=payload.languages,
        match_clock_seconds=payload.match_clock_seconds,
        region_hints=payload.region_hints,
    )
    run_id = await request.app.state.discovery_orchestrator.start_discovery(query)
    return StartDiscoveryResponse(discovery_run_id=run_id)


@router.get("/matches/{match_id}/candidates", response_model=list[CandidateResponse])
async def list_candidates_endpoint(
    match_id: uuid.UUID,
    session: SessionDep,
    candidate_status: Annotated[CandidateStatus | None, Query(alias="status")] = None,
    platform: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CandidateResponse]:
    """List discovered candidates for a match."""
    candidates = await list_candidates(
        session,
        match_id,
        status=candidate_status,
        platform=platform,
        limit=limit,
        offset=offset,
    )
    return [_serialize_candidate(candidate) for candidate in candidates]


@router.get("/matches/{match_id}/agents/health")
async def match_agents_health_endpoint(
    match_id: uuid.UUID,
    request: Request,
    session: SessionDep,
) -> dict[str, object]:
    """Return agent health and recent runs for one match."""
    health = await request.app.state.discovery_orchestrator.health()
    recent_runs = await list_recent_agent_runs(session, match_id=match_id)
    return {
        "agents": {
            name: agent_health.model_dump(mode="json") for name, agent_health in health.items()
        },
        "recent_runs": [_serialize_agent_run(run).model_dump(mode="json") for run in recent_runs],
    }


@router.get("/agents/health")
async def global_agents_health_endpoint(request: Request) -> dict[str, object]:
    """Return health for all registered discovery agents."""
    health = await request.app.state.discovery_orchestrator.health()
    return {
        "agents": {
            name: agent_health.model_dump(mode="json") for name, agent_health in health.items()
        }
    }
