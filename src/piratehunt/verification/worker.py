from __future__ import annotations

import asyncio
import logging
import socket
import tempfile
import time
import uuid
from pathlib import Path

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.ext.asyncio import async_sessionmaker

from piratehunt.agents.types import CandidateStream as CandidateStreamEvent
from piratehunt.config import settings
from piratehunt.db.engine import async_session_maker
from piratehunt.db.models import (
    CandidateStatus,
    CandidateStream,
    VerificationResult,
    VerificationVerdict,
)
from piratehunt.db.repository import (
    get_candidate,
    get_candidate_by_source_url,
    insert_verification_result,
    phash_to_vector,
    search_visual_fingerprints,
    update_candidate_status,
    visual_row_to_dto,
)
from piratehunt.fingerprint.audio import fingerprint_audio_chunk
from piratehunt.fingerprint.extractor import extract_audio_and_keyframes
from piratehunt.fingerprint.types import AudioFingerprint, VisualFingerprint
from piratehunt.fingerprint.visual import fingerprint_keyframes
from piratehunt.index.audio_store import AudioFingerprintStore
from piratehunt.verification.evidence import EvidenceCollector
from piratehunt.verification.gemini_vision import GeminiVisionVerifier
from piratehunt.verification.sampler import sample_clip
from piratehunt.verification.scoring import combined_match_score, verdict_from_scores
from piratehunt.verification.types import (
    CandidateVerified,
    GeminiVerificationSignal,
    PirateConfirmed,
    SampledClip,
)

logger = logging.getLogger(__name__)

VERIFICATION_GROUP = "piratehunt-verification-workers"


class VerificationWorker:
    """Redis consumer that verifies candidate streams against reference fingerprints."""

    def __init__(
        self,
        *,
        redis: Redis,
        session_maker: async_sessionmaker = async_session_maker,
        gemini_verifier: GeminiVisionVerifier | None = None,
        evidence_collector: EvidenceCollector | None = None,
        consumer_name: str | None = None,
    ) -> None:
        self.redis = redis
        self.session_maker = session_maker
        self.gemini_verifier = gemini_verifier or GeminiVisionVerifier()
        self.evidence_collector = evidence_collector or EvidenceCollector()
        self.consumer_name = consumer_name or f"{socket.gethostname()}-verification"
        self.audio_store = AudioFingerprintStore()

    async def ensure_group(self) -> None:
        """Create the Redis consumer group if needed."""
        try:
            await self.redis.xgroup_create(
                settings.redis_candidates_stream,
                VERIFICATION_GROUP,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run_forever(self) -> None:
        """Run verification forever."""
        await self.ensure_group()
        while True:
            processed = await self.run_once(block_ms=5000)
            if not processed:
                await asyncio.sleep(0)

    async def run_once(self, *, block_ms: int = 1000) -> bool:
        """Process one candidate message if available."""
        await self.ensure_group()
        messages = await self.redis.xreadgroup(
            VERIFICATION_GROUP,
            self.consumer_name,
            {settings.redis_candidates_stream: ">"},
            count=1,
            block=block_ms,
        )
        if not messages:
            return False

        for _stream, entries in messages:
            for message_id, fields in entries:
                await self._handle_message(message_id, fields)
                return True
        return False

    async def _handle_message(
        self,
        message_id: bytes | str,
        fields: dict[bytes | str, bytes | str],
    ) -> None:
        raw = fields.get(b"event") or fields.get("event")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if raw is None:
            logger.error("Candidate message missing event field")
            await self.redis.xack(settings.redis_candidates_stream, VERIFICATION_GROUP, message_id)
            return

        event = CandidateStreamEvent.model_validate_json(raw)
        start = time.monotonic()
        try:
            await asyncio.wait_for(
                self.verify_candidate_event(event, start_time=start),
                timeout=settings.verification_total_timeout_seconds,
            )
        except TimeoutError:
            await self._mark_failed(event, start, "timeout")
        except Exception as exc:
            logger.exception("Verification failed for %s", event.source_url)
            await self._mark_failed(event, start, str(exc))
        finally:
            await self.redis.xack(settings.redis_candidates_stream, VERIFICATION_GROUP, message_id)

    async def verify_candidate_event(
        self,
        event: CandidateStreamEvent,
        *,
        start_time: float | None = None,
    ) -> VerificationResult:
        """Verify one candidate event."""
        start = start_time or time.monotonic()
        candidate = await self._resolve_candidate(event)
        if candidate is None:
            msg = f"candidate not found for {event.source_url}"
            raise ValueError(msg)

        async with self.session_maker() as session:
            await update_candidate_status(session, candidate.id, CandidateStatus.verifying)

        with tempfile.TemporaryDirectory(prefix="piratehunt-verify-") as temp_dir_name:
            work_dir = Path(temp_dir_name)
            sampled_clip = await sample_clip(
                candidate.source_url,
                settings.sample_duration_seconds,
                work_dir,
            )
            audio_fps, visual_fps, frame_paths = await _fingerprint_sampled_clip(
                sampled_clip, work_dir
            )
            audio_score = await self._score_audio(candidate.match_id, audio_fps)
            visual_score = await self._score_visual(candidate.match_id, visual_fps)
            combined_score = combined_match_score(
                audio_score,
                visual_score,
                (settings.match_score_audio_weight, settings.match_score_visual_weight),
            )
            gemini_signal = await self._gemini_signal(frame_paths)
            verdict_value = verdict_from_scores(
                combined_score,
                gemini_signal=gemini_signal,
                audio_threshold=settings.audio_match_threshold,
                visual_threshold=settings.visual_match_threshold,
                combined_threshold=settings.combined_pirate_threshold,
                clean_threshold=settings.combined_clean_threshold,
            )
            evidence = await self.evidence_collector.collect(
                candidate,
                sampled_clip,
                frame_paths,
                {
                    "audio_count": len(audio_fps),
                    "visual_count": len(visual_fps),
                },
                {
                    "audio_score": audio_score,
                    "visual_score": visual_score,
                    "combined_score": combined_score,
                },
                gemini_signal,
            )

        status = _candidate_status_for_verdict(verdict_value)
        async with self.session_maker() as session:
            result = await insert_verification_result(
                session,
                candidate_id=candidate.id,
                match_id=candidate.match_id,
                audio_score=audio_score,
                visual_score=visual_score,
                combined_score=combined_score,
                gemini_is_sports=gemini_signal.is_sports_content if gemini_signal else None,
                gemini_detected_sport=gemini_signal.detected_sport if gemini_signal else None,
                gemini_broadcaster_logos=(
                    gemini_signal.broadcaster_logos_detected if gemini_signal else None
                ),
                gemini_confidence=gemini_signal.confidence if gemini_signal else None,
                verdict=VerificationVerdict(verdict_value),
                evidence_artifact_id=evidence.artifact_id,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            await update_candidate_status(
                session,
                candidate.id,
                status,
                notes="inconclusive" if verdict_value == "inconclusive" else None,
            )

        await self._emit_verified(candidate, result)
        return result

    async def _resolve_candidate(self, event: CandidateStreamEvent) -> CandidateStream | None:
        async with self.session_maker() as session:
            candidate = await get_candidate(session, event.id)
            if candidate is not None:
                return candidate
            return await get_candidate_by_source_url(session, event.match_id, event.source_url)

    async def _score_audio(self, match_id: uuid.UUID, audio_fps: list[AudioFingerprint]) -> float:
        best = 0.0
        async with self.session_maker() as session:
            for audio_fp in audio_fps:
                results = await self.audio_store.search_postgres_candidates(
                    session,
                    audio_fp,
                    match_id,
                    threshold=0.0,
                    top_k=1,
                )
                if results:
                    best = max(best, results[0][1])
        return best

    async def _score_visual(
        self, match_id: uuid.UUID, visual_fps: list[VisualFingerprint]
    ) -> float:
        best = 0.0
        async with self.session_maker() as session:
            for visual_fp in visual_fps:
                results = await search_visual_fingerprints(
                    session,
                    phash_to_vector(visual_fp.phash),
                    top_k=1,
                    match_id_filter=match_id,
                )
                if results:
                    row, distance = results[0]
                    visual_row_to_dto(row)
                    best = max(best, max(0.0, 1.0 - (distance / 64.0)))
        return best

    async def _gemini_signal(self, frame_paths: list[Path]) -> GeminiVerificationSignal | None:
        if not settings.enable_gemini_vision:
            return None
        return await self.gemini_verifier.verify(frame_paths, expected_sport="cricket")

    async def _emit_verified(self, candidate: CandidateStream, result: VerificationResult) -> None:
        verified = CandidateVerified(
            candidate_id=candidate.id,
            match_id=candidate.match_id,
            verdict=result.verdict.value,
            combined_score=result.combined_score,
            verification_id=result.id,
        )
        await self.redis.xadd(
            settings.redis_verifications_stream, {"event": verified.model_dump_json()}
        )
        if result.verdict == VerificationVerdict.pirate:
            pirate = PirateConfirmed(
                candidate_id=candidate.id,
                match_id=candidate.match_id,
                source_url=candidate.source_url,
                combined_score=result.combined_score,
                verification_id=result.id,
                evidence_artifact_id=result.evidence_artifact_id,
            )
            await self.redis.xadd(
                settings.redis_pirates_stream, {"event": pirate.model_dump_json()}
            )

    async def _mark_failed(
        self,
        event: CandidateStreamEvent,
        start: float,
        error: str,
    ) -> None:
        candidate = await self._resolve_candidate(event)
        if candidate is None:
            logger.error("Could not mark missing candidate failed: %s", event.source_url)
            return
        async with self.session_maker() as session:
            await insert_verification_result(
                session,
                candidate_id=candidate.id,
                match_id=candidate.match_id,
                audio_score=0.0,
                visual_score=0.0,
                combined_score=0.0,
                verdict=VerificationVerdict.inconclusive,
                latency_ms=int((time.monotonic() - start) * 1000),
                error=error,
            )
            await update_candidate_status(
                session,
                candidate.id,
                CandidateStatus.verification_failed,
                notes=error,
            )


async def _fingerprint_sampled_clip(
    sampled_clip: SampledClip,
    work_dir: Path,
) -> tuple[list[AudioFingerprint], list[VisualFingerprint], list[Path]]:
    windows = await asyncio.to_thread(
        lambda: list(extract_audio_and_keyframes(sampled_clip.path, window_seconds=5))
    )
    audio_fps: list[AudioFingerprint] = []
    visual_fps: list[VisualFingerprint] = []
    frame_paths: list[Path] = []
    for chunk_index, (audio_bytes, keyframes) in enumerate(windows[:3]):
        audio_fps.append(
            await asyncio.to_thread(fingerprint_audio_chunk, audio_bytes, 44100, "candidate")
        )
        visual_chunk = await asyncio.to_thread(
            fingerprint_keyframes,
            keyframes,
            "candidate",
            chunk_index * max(1, len(keyframes)),
        )
        visual_fps.extend(visual_chunk)
        for image in keyframes:
            if len(frame_paths) >= 3:
                break
            frame_path = work_dir / f"frame_{len(frame_paths)}.png"
            image.save(frame_path)
            frame_paths.append(frame_path)
    return audio_fps, visual_fps, frame_paths


def _candidate_status_for_verdict(verdict: str) -> CandidateStatus:
    if verdict == "pirate":
        return CandidateStatus.verified_pirate
    if verdict == "clean":
        return CandidateStatus.verified_clean
    return CandidateStatus.verification_failed


async def run_verification_worker() -> None:
    """Run the verification worker forever."""
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    worker = VerificationWorker(redis=redis)
    try:
        await worker.run_forever()
    finally:
        await redis.aclose()
