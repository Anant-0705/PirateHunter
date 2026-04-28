from __future__ import annotations

import asyncio
import logging
import socket

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.ext.asyncio import async_sessionmaker

from piratehunt.agents.types import CandidateStream
from piratehunt.config import settings
from piratehunt.db.engine import async_session_maker
from piratehunt.db.models import CandidateStatus
from piratehunt.db.repository import get_candidate_by_source_url, update_candidate_status

logger = logging.getLogger(__name__)

CANDIDATE_GROUP = "piratehunt-candidate-workers"


class CandidateConsumer:
    """Phase 3 handoff stub for candidate verification."""

    def __init__(
        self,
        *,
        redis: Redis,
        session_maker: async_sessionmaker = async_session_maker,
        consumer_name: str | None = None,
    ) -> None:
        self.redis = redis
        self.session_maker = session_maker
        self.consumer_name = consumer_name or f"{socket.gethostname()}-candidate"

    async def ensure_group(self) -> None:
        """Create the Redis consumer group if needed."""
        try:
            await self.redis.xgroup_create(
                settings.redis_candidates_stream,
                CANDIDATE_GROUP,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run_forever(self) -> None:
        """Consume candidates until cancelled."""
        await self.ensure_group()
        while True:
            processed = await self.run_once(block_ms=5000)
            if not processed:
                await asyncio.sleep(0)

    async def run_once(self, *, block_ms: int = 1000) -> bool:
        """Process one candidate stream message if available."""
        await self.ensure_group()
        messages = await self.redis.xreadgroup(
            CANDIDATE_GROUP,
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
            msg = "Candidate stream message missing event field"
            raise ValueError(msg)

        candidate = CandidateStream.model_validate_json(raw)
        async with self.session_maker() as session:
            updated = await update_candidate_status(
                session,
                candidate.id,
                CandidateStatus.queued_for_verification,
                notes="Queued by Phase 3 stub consumer",
            )
            if updated is None:
                existing = await get_candidate_by_source_url(
                    session,
                    candidate.match_id,
                    candidate.source_url,
                )
                if existing is not None:
                    await update_candidate_status(
                        session,
                        existing.id,
                        CandidateStatus.queued_for_verification,
                        notes="Queued by Phase 3 stub consumer",
                    )

        logger.info("[STUB] Would verify: %s", candidate.source_url)
        await self.redis.xack(settings.redis_candidates_stream, CANDIDATE_GROUP, message_id)


async def run_candidate_consumer() -> None:
    """Run the candidate consumer forever."""
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    consumer = CandidateConsumer(redis=redis)
    try:
        await consumer.run_forever()
    finally:
        await redis.aclose()
