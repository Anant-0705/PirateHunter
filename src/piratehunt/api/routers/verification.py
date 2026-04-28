from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.api.dependencies import get_session
from piratehunt.db.models import VerificationOverride, VerificationResult, VerificationVerdict
from piratehunt.db.repository import (
    create_verification_override,
    get_verification_for_candidate,
    get_verification_result,
    list_verifications,
)

router = APIRouter(tags=["verification"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class VerificationResponse(BaseModel):
    """API shape for a verification result."""

    id: uuid.UUID
    candidate_id: uuid.UUID
    match_id: uuid.UUID
    audio_score: float
    visual_score: float
    combined_score: float
    gemini_is_sports: bool | None
    gemini_detected_sport: str | None
    gemini_broadcaster_logos: list[str] | None
    gemini_confidence: float | None
    verdict: VerificationVerdict
    evidence_artifact_id: str | None
    evidence_urls: dict[str, str]
    verified_at: str
    latency_ms: int
    error: str | None


class OverrideRequest(BaseModel):
    """Manual override request body."""

    verdict: VerificationVerdict
    notes: str | None = None
    overridden_by: str = Field(default="manual")


class OverrideResponse(BaseModel):
    """Manual override response."""

    id: uuid.UUID
    verification_id: uuid.UUID
    original_verdict: VerificationVerdict
    override_verdict: VerificationVerdict
    notes: str | None
    overridden_by: str
    overridden_at: str


def _serialize_verification(result: VerificationResult) -> VerificationResponse:
    evidence_urls = {}
    if result.evidence_artifact_id:
        evidence_urls["artifact"] = result.evidence_artifact_id
    return VerificationResponse(
        id=result.id,
        candidate_id=result.candidate_id,
        match_id=result.match_id,
        audio_score=result.audio_score,
        visual_score=result.visual_score,
        combined_score=result.combined_score,
        gemini_is_sports=result.gemini_is_sports,
        gemini_detected_sport=result.gemini_detected_sport,
        gemini_broadcaster_logos=result.gemini_broadcaster_logos,
        gemini_confidence=result.gemini_confidence,
        verdict=result.verdict,
        evidence_artifact_id=result.evidence_artifact_id,
        evidence_urls=evidence_urls,
        verified_at=result.verified_at.isoformat(),
        latency_ms=result.latency_ms,
        error=result.error,
    )


def _serialize_override(override: VerificationOverride) -> OverrideResponse:
    return OverrideResponse(
        id=override.id,
        verification_id=override.verification_id,
        original_verdict=override.original_verdict,
        override_verdict=override.override_verdict,
        notes=override.notes,
        overridden_by=override.overridden_by,
        overridden_at=override.overridden_at.isoformat(),
    )


@router.get("/matches/{match_id}/verifications", response_model=list[VerificationResponse])
async def list_verifications_endpoint(
    match_id: uuid.UUID,
    session: SessionDep,
    verdict: VerificationVerdict | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[VerificationResponse]:
    """List verification results for a match."""
    results = await list_verifications(
        session,
        match_id,
        verdict=verdict,
        limit=limit,
        offset=offset,
    )
    return [_serialize_verification(result) for result in results]


@router.get("/candidates/{candidate_id}/verification", response_model=VerificationResponse)
async def candidate_verification_endpoint(
    candidate_id: uuid.UUID,
    session: SessionDep,
) -> VerificationResponse:
    """Fetch a single candidate verification result."""
    result = await get_verification_for_candidate(session, candidate_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Verification not found")
    return _serialize_verification(result)


@router.get("/matches/{match_id}/pirates", response_model=list[VerificationResponse])
async def pirates_endpoint(
    match_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[VerificationResponse]:
    """Return confirmed pirate verification results."""
    results = await list_verifications(
        session,
        match_id,
        verdict=VerificationVerdict.pirate,
        limit=limit,
        offset=offset,
    )
    return [_serialize_verification(result) for result in results]


@router.post("/verifications/{verification_id}/override", response_model=OverrideResponse)
async def override_verification_endpoint(
    verification_id: uuid.UUID,
    payload: OverrideRequest,
    session: SessionDep,
) -> OverrideResponse:
    """Record a manual override for a verification result."""
    result = await get_verification_result(session, verification_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Verification not found")
    override = await create_verification_override(
        session,
        verification_id=verification_id,
        verdict=payload.verdict,
        notes=payload.notes,
        overridden_by=payload.overridden_by,
    )
    if override is None:
        raise HTTPException(status_code=404, detail="Verification not found")
    return _serialize_override(override)
