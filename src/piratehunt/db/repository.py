from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.agents.types import CandidateStream as CandidateStreamDTO
from piratehunt.db.models import (
    AgentRun,
    AgentRunStatus,
    AudioFingerprint,
    CandidateStatus,
    CandidateStream,
    Match,
    MatchStatus,
    VerificationOverride,
    VerificationResult,
    VerificationVerdict,
    VisualFingerprint,
)
from piratehunt.fingerprint.types import (
    AudioFingerprint as AudioFingerprintDTO,
)
from piratehunt.fingerprint.types import (
    VisualFingerprint as VisualFingerprintDTO,
)


def phash_to_vector(phash: str) -> list[float]:
    """Convert a 64-bit pHash hex string into a pgvector-compatible bit vector."""
    hex_str = phash.removeprefix("0x").zfill(16)
    value = int(hex_str, 16)
    return [float((value >> bit) & 1) for bit in range(64)]


def audio_row_to_dto(row: AudioFingerprint) -> AudioFingerprintDTO:
    """Convert a persisted audio row into the Phase 1 fingerprint DTO."""
    fingerprint_hash = row.chromaprint_bytes.decode("utf-8", errors="ignore")
    return AudioFingerprintDTO(
        fingerprint_hash=fingerprint_hash,
        duration_s=row.duration_seconds,
        created_at=row.created_at,
        source_id=str(row.match_id),
        match_id=row.match_id,
        chunk_index=row.chunk_index,
        start_seconds=row.start_seconds,
        fallback_hash=row.fallback_hash,
    )


def visual_row_to_dto(row: VisualFingerprint) -> VisualFingerprintDTO:
    """Convert a persisted visual row into the Phase 1 fingerprint DTO."""
    return VisualFingerprintDTO(
        phash=row.phash,
        dhash=row.dhash,
        frame_index=row.frame_index,
        source_id=str(row.match_id),
        match_id=row.match_id,
        timestamp_seconds=row.timestamp_seconds,
    )


async def create_match(session: AsyncSession, name: str, source_url: str) -> Match:
    """Create a pending match row."""
    match = Match(name=name, source_url=source_url, status=MatchStatus.pending)
    session.add(match)
    await session.commit()
    await session.refresh(match)
    return match


async def update_match_status(
    session: AsyncSession,
    match_id: uuid.UUID,
    status: MatchStatus,
    *,
    error: str | None = None,
) -> Match | None:
    """Update match status and lifecycle timestamps."""
    match = await session.get(Match, match_id)
    if match is None:
        return None

    now = datetime.utcnow()
    match.status = status
    match.error = error
    if status == MatchStatus.ingesting:
        match.started_at = match.started_at or now
        match.finished_at = None
    if status in {MatchStatus.ready, MatchStatus.failed}:
        match.finished_at = now

    await session.commit()
    await session.refresh(match)
    return match


async def bulk_insert_audio_fingerprints(
    session: AsyncSession,
    match_id: uuid.UUID,
    fingerprints: list[AudioFingerprintDTO],
) -> list[AudioFingerprint]:
    """Bulk insert audio fingerprints for a match."""
    rows = [
        AudioFingerprint(
            match_id=match_id,
            chunk_index=fp.chunk_index if fp.chunk_index is not None else idx,
            start_seconds=fp.start_seconds if fp.start_seconds is not None else idx * fp.duration_s,
            duration_seconds=fp.duration_s,
            chromaprint_bytes=fp.fingerprint_hash.encode("utf-8"),
            fallback_hash=fp.fallback_hash,
        )
        for idx, fp in enumerate(fingerprints)
    ]
    session.add_all(rows)
    await session.commit()
    return rows


async def bulk_insert_visual_fingerprints(
    session: AsyncSession,
    match_id: uuid.UUID,
    fingerprints: list[VisualFingerprintDTO],
) -> list[VisualFingerprint]:
    """Bulk insert visual fingerprints for a match."""
    rows = [
        VisualFingerprint(
            match_id=match_id,
            frame_index=fp.frame_index,
            timestamp_seconds=(
                fp.timestamp_seconds if fp.timestamp_seconds is not None else float(fp.frame_index)
            ),
            phash=fp.phash,
            dhash=fp.dhash,
            phash_vector=phash_to_vector(fp.phash),
        )
        for fp in fingerprints
    ]
    session.add_all(rows)
    await session.commit()
    return rows


async def get_match(session: AsyncSession, match_id: uuid.UUID) -> Match | None:
    """Fetch a match by ID."""
    return await session.get(Match, match_id)


async def list_matches(
    session: AsyncSession,
    *,
    status: MatchStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Match]:
    """List matches with optional status filtering."""
    stmt = select(Match).order_by(Match.created_at.desc()).limit(limit).offset(offset)
    if status is not None:
        stmt = stmt.where(Match.status == status)
    return list((await session.scalars(stmt)).all())


async def count_fingerprints(session: AsyncSession, match_id: uuid.UUID) -> tuple[int, int]:
    """Return audio and visual fingerprint counts for a match."""
    audio_count = await session.scalar(
        select(func.count())
        .select_from(AudioFingerprint)
        .where(AudioFingerprint.match_id == match_id)
    )
    visual_count = await session.scalar(
        select(func.count())
        .select_from(VisualFingerprint)
        .where(VisualFingerprint.match_id == match_id)
    )
    return int(audio_count or 0), int(visual_count or 0)


async def list_audio_fingerprints_for_match(
    session: AsyncSession,
    match_id: uuid.UUID,
    *,
    chunk_start: int | None = None,
    chunk_end: int | None = None,
) -> list[AudioFingerprint]:
    """List audio fingerprints for a match, optionally constrained by chunk index."""
    stmt = select(AudioFingerprint).where(AudioFingerprint.match_id == match_id)
    if chunk_start is not None:
        stmt = stmt.where(AudioFingerprint.chunk_index >= chunk_start)
    if chunk_end is not None:
        stmt = stmt.where(AudioFingerprint.chunk_index <= chunk_end)
    stmt = stmt.order_by(AudioFingerprint.chunk_index)
    return list((await session.scalars(stmt)).all())


async def list_ready_fingerprints(
    session: AsyncSession,
) -> tuple[list[AudioFingerprint], list[VisualFingerprint]]:
    """Load all fingerprints for ready matches for in-memory cache hydration."""
    ready_ids = select(Match.id).where(Match.status == MatchStatus.ready)
    audio = list(
        (
            await session.scalars(
                select(AudioFingerprint).where(AudioFingerprint.match_id.in_(ready_ids))
            )
        ).all()
    )
    visual = list(
        (
            await session.scalars(
                select(VisualFingerprint).where(VisualFingerprint.match_id.in_(ready_ids))
            )
        ).all()
    )
    return audio, visual


async def search_visual_fingerprints(
    session: AsyncSession,
    query_vector: list[float],
    top_k: int,
    match_id_filter: uuid.UUID | None = None,
) -> list[tuple[VisualFingerprint, float]]:
    """Search visual fingerprints by pgvector L2 distance."""
    distance = VisualFingerprint.phash_vector.l2_distance(query_vector).label("distance")
    stmt: Select[tuple[VisualFingerprint, Any]] = (
        select(VisualFingerprint, distance).order_by(distance).limit(top_k)
    )
    if match_id_filter is not None:
        stmt = stmt.where(VisualFingerprint.match_id == match_id_filter)

    result = await session.execute(stmt)
    return [(row[0], float(row[1])) for row in result.all()]


async def insert_candidate_stream(
    session: AsyncSession,
    candidate: CandidateStreamDTO,
) -> CandidateStream | None:
    """Insert a candidate stream, deduping by match/source URL."""
    stmt = (
        pg_insert(CandidateStream)
        .values(
            id=candidate.id,
            match_id=candidate.match_id,
            source_platform=candidate.source_platform,
            source_url=candidate.source_url,
            discovered_at=candidate.discovered_at,
            discovered_by_agent=candidate.discovered_by_agent,
            candidate_metadata=candidate.metadata,
            confidence_hint=candidate.confidence_hint,
            status=CandidateStatus.discovered,
        )
        .on_conflict_do_nothing(
            index_elements=[CandidateStream.match_id, CandidateStream.source_url]
        )
        .returning(CandidateStream)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    await session.commit()
    return row


async def list_candidates(
    session: AsyncSession,
    match_id: uuid.UUID,
    *,
    status: CandidateStatus | None = None,
    platform: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CandidateStream]:
    """List discovered candidates for a match."""
    stmt = (
        select(CandidateStream)
        .where(CandidateStream.match_id == match_id)
        .order_by(CandidateStream.discovered_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status is not None:
        stmt = stmt.where(CandidateStream.status == status)
    if platform is not None:
        stmt = stmt.where(CandidateStream.source_platform == platform)
    return list((await session.scalars(stmt)).all())


async def update_candidate_status(
    session: AsyncSession,
    candidate_id: uuid.UUID,
    new_status: CandidateStatus,
    *,
    notes: str | None = None,
) -> CandidateStream | None:
    """Update a candidate verification status."""
    candidate = await session.get(CandidateStream, candidate_id)
    if candidate is None:
        return None
    candidate.status = new_status
    candidate.notes = notes
    if new_status in {
        CandidateStatus.verified_pirate,
        CandidateStatus.verified_clean,
        CandidateStatus.verification_failed,
    }:
        candidate.verified_at = datetime.utcnow()
    await session.commit()
    await session.refresh(candidate)
    return candidate


async def get_candidate_by_source_url(
    session: AsyncSession,
    match_id: uuid.UUID,
    source_url: str,
) -> CandidateStream | None:
    """Fetch a candidate by its dedupe key."""
    stmt = select(CandidateStream).where(
        CandidateStream.match_id == match_id,
        CandidateStream.source_url == source_url,
    )
    return (await session.scalars(stmt)).first()


async def create_agent_run(
    session: AsyncSession,
    match_id: uuid.UUID,
    agent_name: str,
) -> AgentRun:
    """Create an operational record for one agent run."""
    run = AgentRun(match_id=match_id, agent_name=agent_name)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def complete_agent_run(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: AgentRunStatus,
    *,
    candidates_found: int = 0,
    error: str | None = None,
) -> AgentRun | None:
    """Mark an agent run complete."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        return None
    run.status = status
    run.finished_at = datetime.utcnow()
    run.candidates_found = candidates_found
    run.error = error
    await session.commit()
    await session.refresh(run)
    return run


async def list_recent_agent_runs(
    session: AsyncSession,
    *,
    match_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[AgentRun]:
    """List recent discovery agent runs."""
    stmt = select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
    if match_id is not None:
        stmt = stmt.where(AgentRun.match_id == match_id)
    return list((await session.scalars(stmt)).all())


async def get_candidate(session: AsyncSession, candidate_id: uuid.UUID) -> CandidateStream | None:
    """Fetch a candidate stream by ID."""
    return await session.get(CandidateStream, candidate_id)


async def insert_verification_result(
    session: AsyncSession,
    *,
    candidate_id: uuid.UUID,
    match_id: uuid.UUID,
    audio_score: float,
    visual_score: float,
    combined_score: float,
    verdict: VerificationVerdict,
    latency_ms: int,
    gemini_is_sports: bool | None = None,
    gemini_detected_sport: str | None = None,
    gemini_broadcaster_logos: list[str] | None = None,
    gemini_confidence: float | None = None,
    evidence_artifact_id: str | None = None,
    error: str | None = None,
) -> VerificationResult:
    """Insert or replace the verification result for a candidate."""
    existing = await get_verification_for_candidate(session, candidate_id)
    if existing is not None:
        existing.audio_score = audio_score
        existing.visual_score = visual_score
        existing.combined_score = combined_score
        existing.gemini_is_sports = gemini_is_sports
        existing.gemini_detected_sport = gemini_detected_sport
        existing.gemini_broadcaster_logos = gemini_broadcaster_logos
        existing.gemini_confidence = gemini_confidence
        existing.verdict = verdict
        existing.evidence_artifact_id = evidence_artifact_id
        existing.verified_at = datetime.utcnow()
        existing.latency_ms = latency_ms
        existing.error = error
        await session.commit()
        await session.refresh(existing)
        return existing

    result = VerificationResult(
        candidate_id=candidate_id,
        match_id=match_id,
        audio_score=audio_score,
        visual_score=visual_score,
        combined_score=combined_score,
        gemini_is_sports=gemini_is_sports,
        gemini_detected_sport=gemini_detected_sport,
        gemini_broadcaster_logos=gemini_broadcaster_logos,
        gemini_confidence=gemini_confidence,
        verdict=verdict,
        evidence_artifact_id=evidence_artifact_id,
        latency_ms=latency_ms,
        error=error,
    )
    session.add(result)
    await session.commit()
    await session.refresh(result)
    return result


async def get_verification_for_candidate(
    session: AsyncSession,
    candidate_id: uuid.UUID,
) -> VerificationResult | None:
    """Fetch the verification result for one candidate."""
    stmt = select(VerificationResult).where(VerificationResult.candidate_id == candidate_id)
    return (await session.scalars(stmt)).first()


async def get_verification_result(
    session: AsyncSession,
    verification_id: uuid.UUID,
) -> VerificationResult | None:
    """Fetch a verification result by ID."""
    return await session.get(VerificationResult, verification_id)


async def list_verifications(
    session: AsyncSession,
    match_id: uuid.UUID,
    *,
    verdict: VerificationVerdict | None = None,
    since: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[VerificationResult]:
    """List verification results for a match."""
    stmt = (
        select(VerificationResult)
        .where(VerificationResult.match_id == match_id)
        .order_by(VerificationResult.verified_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if verdict is not None:
        stmt = stmt.where(VerificationResult.verdict == verdict)
    if since is not None:
        stmt = stmt.where(VerificationResult.verified_at >= since)
    return list((await session.scalars(stmt)).all())


async def latest_verifications_per_match(
    session: AsyncSession,
    match_id: uuid.UUID,
    *,
    limit: int = 20,
) -> list[VerificationResult]:
    """Return newest verification results for a match."""
    stmt = (
        select(VerificationResult)
        .where(VerificationResult.match_id == match_id)
        .order_by(VerificationResult.verified_at.desc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


async def create_verification_override(
    session: AsyncSession,
    *,
    verification_id: uuid.UUID,
    verdict: VerificationVerdict,
    notes: str | None,
    overridden_by: str = "system",
) -> VerificationOverride | None:
    """Record a manual override without deleting the original verdict."""
    verification = await session.get(VerificationResult, verification_id)
    if verification is None:
        return None
    override = VerificationOverride(
        verification_id=verification_id,
        original_verdict=verification.verdict,
        override_verdict=verdict,
        notes=notes,
        overridden_by=overridden_by,
    )
    session.add(override)
    await session.commit()
    await session.refresh(override)
    return override


async def latest_successful_verification_time(session: AsyncSession) -> datetime | None:
    """Return the newest successful verification timestamp."""
    return await session.scalar(
        select(func.max(VerificationResult.verified_at)).where(VerificationResult.error.is_(None))
    )
