from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Iterable
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.ext.asyncio import async_sessionmaker

from piratehunt.config import settings
from piratehunt.db.engine import async_session_maker
from piratehunt.db.models import MatchStatus
from piratehunt.db.repository import (
    bulk_insert_audio_fingerprints,
    bulk_insert_visual_fingerprints,
    update_match_status,
)
from piratehunt.fingerprint.audio import fingerprint_audio_chunk
from piratehunt.fingerprint.extractor import extract_audio_and_keyframes
from piratehunt.fingerprint.types import AudioFingerprint, VisualFingerprint
from piratehunt.fingerprint.visual import fingerprint_keyframes
from piratehunt.index.audio_store import AudioFingerprintStore
from piratehunt.index.faiss_store import VisualHashIndex
from piratehunt.ingestion.events import IngestionCompleted, IngestionFailed, IngestionProgress
from piratehunt.ingestion.producer import decode_stream_event

logger = logging.getLogger(__name__)

STREAM_GROUP = "piratehunt-workers"


class IngestionWorker:
    """Redis Streams consumer that persists fingerprints for requested matches."""

    def __init__(
        self,
        *,
        redis: Redis,
        session_maker: async_sessionmaker = async_session_maker,
        audio_store: AudioFingerprintStore | None = None,
        visual_index: VisualHashIndex | None = None,
        consumer_name: str | None = None,
    ) -> None:
        self.redis = redis
        self.session_maker = session_maker
        self.audio_store = audio_store or AudioFingerprintStore()
        self.visual_index = visual_index or VisualHashIndex()
        self.consumer_name = consumer_name or f"{socket.gethostname()}-ingest"

    async def ensure_group(self) -> None:
        """Create the Redis consumer group if it does not already exist."""
        try:
            await self.redis.xgroup_create(
                settings.redis_ingest_stream,
                STREAM_GROUP,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run_forever(self) -> None:
        """Run the worker until cancelled."""
        await self.ensure_group()
        logger.info("Ingestion worker listening on %s", settings.redis_ingest_stream)
        while True:
            processed = await self.run_once(block_ms=5000)
            if not processed:
                await asyncio.sleep(0)

    async def run_once(self, *, block_ms: int = 1000) -> bool:
        """Read and process one stream event, returning whether work was done."""
        await self.ensure_group()
        messages = await self.redis.xreadgroup(
            STREAM_GROUP,
            self.consumer_name,
            {settings.redis_ingest_stream: ">"},
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
        self, message_id: bytes | str, fields: dict[bytes | str, bytes | str]
    ) -> None:
        event = decode_stream_event(fields)
        try:
            await self.process_event(event.match_id, event.source_url)
            await self.redis.xack(settings.redis_ingest_stream, STREAM_GROUP, message_id)
        except Exception as exc:
            logger.exception("Ingestion failed for match %s", event.match_id)
            async with self.session_maker() as session:
                await update_match_status(
                    session,
                    event.match_id,
                    MatchStatus.failed,
                    error=str(exc),
                )
            failed = IngestionFailed(match_id=event.match_id, error=str(exc))
            await self.redis.xadd(settings.redis_events_stream, {"event": failed.model_dump_json()})
            await self.redis.xack(settings.redis_ingest_stream, STREAM_GROUP, message_id)

    async def process_event(self, match_id: UUID, source_url: str) -> None:
        """Fingerprint a source URL and persist the results."""
        if not source_url.strip():
            raise ValueError("source_url is required")

        async with self.session_maker() as session:
            await update_match_status(session, match_id, MatchStatus.ingesting)

        windows = await asyncio.to_thread(lambda: list(extract_audio_and_keyframes(source_url)))
        audio_batch: list[AudioFingerprint] = []
        visual_batch: list[VisualFingerprint] = []
        total_chunks = 0

        for chunk_index, (audio_bytes, keyframes) in enumerate(windows):
            start_seconds = float(chunk_index * 5)
            audio_fp = await asyncio.to_thread(
                fingerprint_audio_chunk,
                audio_bytes,
                44100,
                str(match_id),
            )
            audio_fp.match_id = match_id
            audio_fp.chunk_index = chunk_index
            audio_fp.start_seconds = start_seconds
            if _looks_like_sha256(audio_fp.fingerprint_hash):
                audio_fp.fallback_hash = audio_fp.fingerprint_hash
            audio_batch.append(audio_fp)

            visual_fps = await asyncio.to_thread(
                fingerprint_keyframes,
                keyframes,
                str(match_id),
                chunk_index * max(1, len(keyframes)),
            )
            for offset, visual_fp in enumerate(visual_fps):
                visual_fp.match_id = match_id
                visual_fp.timestamp_seconds = start_seconds + float(offset)
            visual_batch.extend(visual_fps)

            total_chunks += 1
            if total_chunks % settings.ingestion_batch_size == 0:
                await self._flush(match_id, audio_batch, visual_batch)
                audio_batch.clear()
                visual_batch.clear()
                await self._emit_progress(match_id, total_chunks)

        await self._flush(match_id, audio_batch, visual_batch)
        await self._emit_progress(match_id, total_chunks)
        async with self.session_maker() as session:
            await update_match_status(session, match_id, MatchStatus.ready)
        completed = IngestionCompleted(match_id=match_id, total_chunks=total_chunks)
        await self.redis.xadd(settings.redis_events_stream, {"event": completed.model_dump_json()})

    async def _flush(
        self,
        match_id: UUID,
        audio_fingerprints: list[AudioFingerprint],
        visual_fingerprints: list[VisualFingerprint],
    ) -> None:
        """Persist and cache a batch of fingerprints."""
        if not audio_fingerprints and not visual_fingerprints:
            return

        async with self.session_maker() as session:
            if audio_fingerprints:
                await bulk_insert_audio_fingerprints(session, match_id, audio_fingerprints)
            if visual_fingerprints:
                await bulk_insert_visual_fingerprints(session, match_id, visual_fingerprints)

        self.audio_store.add(list(audio_fingerprints))
        if visual_fingerprints:
            self.visual_index.add(list(visual_fingerprints))

    async def _emit_progress(self, match_id: UUID, chunks_processed: int) -> None:
        """Emit an ingestion progress event."""
        progress = IngestionProgress(match_id=match_id, chunks_processed=chunks_processed)
        await self.redis.xadd(settings.redis_events_stream, {"event": progress.model_dump_json()})


def _looks_like_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


async def run_worker() -> None:
    """Create dependencies and run the worker forever."""
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    worker = IngestionWorker(redis=redis)
    try:
        await worker.run_forever()
    finally:
        await redis.aclose()


async def process_events(events: Iterable[tuple[UUID, str]]) -> None:
    """Small helper for tests to process explicit events without Redis reads."""
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    worker = IngestionWorker(redis=redis)
    try:
        for match_id, source_url in events:
            await worker.process_event(match_id, source_url)
    finally:
        await redis.aclose()
