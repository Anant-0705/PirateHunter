from __future__ import annotations

import asyncio
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field, HttpUrl
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.api.dependencies import get_redis, get_session
from piratehunt.config import settings
from piratehunt.db.models import Match, MatchStatus
from piratehunt.db.repository import (
    count_fingerprints,
    get_match,
    list_matches,
    phash_to_vector,
    search_visual_fingerprints,
    visual_row_to_dto,
)
from piratehunt.fingerprint.audio import fingerprint_audio_chunk
from piratehunt.fingerprint.extractor import extract_audio_and_keyframes
from piratehunt.fingerprint.types import AudioFingerprint, VisualFingerprint
from piratehunt.fingerprint.visual import fingerprint_keyframes
from piratehunt.index.audio_store import AudioFingerprintStore
from piratehunt.index.faiss_store import VisualHashIndex
from piratehunt.ingestion.producer import enqueue_ingestion

router = APIRouter(tags=["matches"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
UploadFileDep = Annotated[UploadFile | None, File()]


class CreateMatchRequest(BaseModel):
    """Request body for creating an ingestible match."""

    name: str = Field(min_length=1, max_length=255)
    source_url: HttpUrl


class CreateMatchResponse(BaseModel):
    """Response returned after enqueueing ingestion."""

    match_id: uuid.UUID
    status_url: str
    status: MatchStatus


class MatchResponse(BaseModel):
    """Match metadata with persisted fingerprint counts."""

    id: uuid.UUID
    name: str
    source_url: str
    status: MatchStatus
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    audio_fingerprint_count: int
    visual_fingerprint_count: int


class RemoteCheckRequest(BaseModel):
    """JSON body for checking a remote candidate URL."""

    source_url: HttpUrl


class MatchEvidence(BaseModel):
    """Evidence fields returned for a candidate match."""

    audio_chunk_index: int | None = None
    visual_frame_index: int | None = None
    time_offset_seconds: float | None = None


class MatchCheckResult(BaseModel):
    """Ranked result for a match check."""

    match_id: uuid.UUID
    match_name: str
    audio_score: float
    visual_score: float
    combined_score: float
    evidence: MatchEvidence


def _serialize_match(match: Match, audio_count: int, visual_count: int) -> MatchResponse:
    return MatchResponse(
        id=match.id,
        name=match.name,
        source_url=match.source_url,
        status=match.status,
        created_at=match.created_at.isoformat(),
        started_at=match.started_at.isoformat() if match.started_at else None,
        finished_at=match.finished_at.isoformat() if match.finished_at else None,
        error=match.error,
        audio_fingerprint_count=audio_count,
        visual_fingerprint_count=visual_count,
    )


@router.post("/matches", status_code=status.HTTP_202_ACCEPTED, response_model=CreateMatchResponse)
async def create_match_endpoint(
    payload: CreateMatchRequest,
    request: Request,
    session: SessionDep,
    redis: RedisDep,
) -> CreateMatchResponse:
    """Create a match and enqueue asynchronous ingestion."""
    from piratehunt.db.repository import create_match

    match = await create_match(session, payload.name, str(payload.source_url))
    await enqueue_ingestion(redis, match.id, match.source_url)
    return CreateMatchResponse(
        match_id=match.id,
        status_url=str(request.url_for("get_match_endpoint", match_id=str(match.id))),
        status=match.status,
    )


@router.get("/matches/{match_id}", response_model=MatchResponse)
async def get_match_endpoint(
    match_id: uuid.UUID,
    session: SessionDep,
) -> MatchResponse:
    """Fetch match metadata and fingerprint counts."""
    match = await get_match(session, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    audio_count, visual_count = await count_fingerprints(session, match_id)
    return _serialize_match(match, audio_count, visual_count)


@router.get("/matches", response_model=list[MatchResponse])
async def list_matches_endpoint(
    session: SessionDep,
    status_filter: Annotated[MatchStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MatchResponse]:
    """List matches with pagination and optional status filtering."""
    matches = await list_matches(session, status=status_filter, limit=limit, offset=offset)
    responses = []
    for match in matches:
        audio_count, visual_count = await count_fingerprints(session, match.id)
        responses.append(_serialize_match(match, audio_count, visual_count))
    return responses


@router.post("/match/check", response_model=list[MatchCheckResult])
async def check_match_endpoint(  # noqa: C901
    request: Request,
    session: SessionDep,
    file: UploadFileDep = None,
) -> list[MatchCheckResult]:
    """Fingerprint a short candidate sample and search the audio and visual indices."""
    source: str | Path
    temp_path: Path | None = None

    if file is not None:
        suffix = Path(file.filename or "candidate.mp4").suffix or ".mp4"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
        content = await file.read()
        await asyncio.to_thread(temp_path.write_bytes, content)
        source = temp_path
    else:
        try:
            payload = RemoteCheckRequest.model_validate(await request.json())
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail="Provide a file or JSON source_url"
            ) from exc
        source = str(payload.source_url)

    try:
        audio_queries, visual_queries = await _fingerprint_sample(source)
    finally:
        if temp_path is not None:
            await asyncio.to_thread(temp_path.unlink, missing_ok=True)

    if not audio_queries and not visual_queries:
        return []

    audio_store: AudioFingerprintStore = request.app.state.audio_store
    visual_index: VisualHashIndex = request.app.state.visual_index
    matches_by_id = {
        match.id: match for match in await list_matches(session, status=MatchStatus.ready)
    }
    scored: dict[uuid.UUID, MatchCheckResult] = {}

    for audio_query in audio_queries:
        audio_results = audio_store.search(
            audio_query,
            threshold=settings.audio_match_threshold,
            top_k=10,
        )
        if not audio_results:
            for ready_match in matches_by_id.values():
                audio_results.extend(
                    await audio_store.search_postgres_candidates(
                        session,
                        audio_query,
                        ready_match.id,
                        threshold=settings.audio_match_threshold,
                        top_k=3,
                    )
                )
        for candidate, audio_score in audio_results:
            if candidate.match_id is None or candidate.match_id not in matches_by_id:
                continue
            current = scored.get(candidate.match_id)
            evidence = MatchEvidence(
                audio_chunk_index=candidate.chunk_index,
                time_offset_seconds=candidate.start_seconds,
            )
            if current is None or audio_score > current.audio_score:
                scored[candidate.match_id] = MatchCheckResult(
                    match_id=candidate.match_id,
                    match_name=matches_by_id[candidate.match_id].name,
                    audio_score=audio_score,
                    visual_score=current.visual_score if current else 0.0,
                    combined_score=0.0,
                    evidence=evidence,
                )

    for visual_query in visual_queries:
        visual_hits = visual_index.search(visual_query, top_k=10) if len(visual_index) else []
        if not visual_hits:
            rows = await search_visual_fingerprints(
                session,
                phash_to_vector(visual_query.phash),
                top_k=10,
            )
            visual_hits = [(visual_row_to_dto(row), distance) for row, distance in rows]

        for candidate, distance in visual_hits:
            if distance > settings.visual_match_threshold:
                continue
            if candidate.match_id is None or candidate.match_id not in matches_by_id:
                continue
            visual_score = max(0.0, 1.0 - (distance / 64.0))
            current = scored.get(candidate.match_id)
            if current is None:
                scored[candidate.match_id] = MatchCheckResult(
                    match_id=candidate.match_id,
                    match_name=matches_by_id[candidate.match_id].name,
                    audio_score=0.0,
                    visual_score=visual_score,
                    combined_score=0.0,
                    evidence=MatchEvidence(
                        visual_frame_index=candidate.frame_index,
                        time_offset_seconds=candidate.timestamp_seconds,
                    ),
                )
            elif visual_score > current.visual_score:
                current.visual_score = visual_score
                current.evidence.visual_frame_index = candidate.frame_index
                current.evidence.time_offset_seconds = (
                    current.evidence.time_offset_seconds or candidate.timestamp_seconds
                )

    for result in scored.values():
        result.combined_score = (
            result.audio_score * settings.match_score_audio_weight
            + result.visual_score * settings.match_score_visual_weight
        )

    return sorted(scored.values(), key=lambda result: result.combined_score, reverse=True)


async def _fingerprint_sample(
    source: str | Path,
) -> tuple[list[AudioFingerprint], list[VisualFingerprint]]:
    """Extract and fingerprint a 5-15 second candidate sample."""
    windows = await asyncio.to_thread(
        lambda: _take_windows(extract_audio_and_keyframes(source, window_seconds=5), limit=3)
    )
    audio_queries: list[AudioFingerprint] = []
    visual_queries: list[VisualFingerprint] = []
    for chunk_index, (audio_bytes, keyframes) in enumerate(windows):
        audio_queries.append(
            await asyncio.to_thread(fingerprint_audio_chunk, audio_bytes, 44100, "candidate")
        )
        visual_queries.extend(
            await asyncio.to_thread(
                fingerprint_keyframes,
                keyframes,
                "candidate",
                chunk_index * max(1, len(keyframes)),
            )
        )
    return audio_queries, visual_queries


def _take_windows(
    iterator: Iterator[tuple[bytes, list[object]]], *, limit: int
) -> list[tuple[bytes, list[object]]]:
    windows: list[tuple[bytes, list[object]]] = []
    for item in iterator:
        windows.append(item)
        if len(windows) >= limit:
            break
    return windows
