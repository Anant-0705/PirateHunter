from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from piratehunt.config import settings
from piratehunt.db.models import CandidateStream, Match, VerificationResult
from piratehunt.dmca.generator import DMCAGenerator
from piratehunt.dmca.rights_holders import RightsHolderRegistry
from piratehunt.dmca.tracker import TakedownTracker
from piratehunt.dmca.types import RightsHolderInfo

logger = logging.getLogger(__name__)


class DMCAWorker:
    """Consumer of PirateConfirmed events; generates DMCA notices."""

    def __init__(self, redis_client: redis.Redis, db_session: sessionmaker):
        """Initialize DMCA worker."""
        self.redis = redis_client
        self.db_session = db_session
        self.generator = DMCAGenerator()
        self.tracker = TakedownTracker()
        self.registry = RightsHolderRegistry()

    async def process_event(self, event_data: dict) -> Optional[str]:
        """
        Process a PirateConfirmed event from the stream.

        Args:
            event_data: Event dict with verification_result_id, candidate_id, match_id

        Returns:
            Takedown case ID if successful, None if failed
        """
        verification_result_id = event_data.get("verification_result_id")
        candidate_id = event_data.get("candidate_id")
        match_id = event_data.get("match_id")

        if not all([verification_result_id, candidate_id, match_id]):
            logger.error(f"Invalid event data: {event_data}")
            return None

        try:
            async with self.db_session() as session:
                # Fetch required data
                vresult = await session.get(
                    VerificationResult, verification_result_id
                )
                candidate = await session.get(CandidateStream, candidate_id)
                match = await session.get(Match, match_id)

                if not all([vresult, candidate, match]):
                    logger.error(
                        f"Could not fetch required data for event {event_data}"
                    )
                    return None

                # Get rights holder (use default or assigned)
                rights_holder = None
                if event_data.get("rights_holder_id"):
                    rights_holder = await self.registry.get_rights_holder(
                        session, event_data["rights_holder_id"]
                    )

                if not rights_holder:
                    # Use default rights holder
                    if settings.dmca_default_rights_holder_id:
                        rights_holder = await self.registry.get_rights_holder(
                            session, settings.dmca_default_rights_holder_id
                        )
                    else:
                        # Create minimal rights holder info
                        rights_holder = RightsHolderInfo(
                            id="default",
                            name="Default Rights Holder",
                            legal_email="rights@example.com",
                            address="123 Example St",
                            authorized_agent="Legal Department",
                            signature_block="Signed,\nLegal Department",
                        )

                # Generate DMCA notice
                try:
                    draft_notice = await asyncio.wait_for(
                        self.generator.generate(
                            {
                                "audio_score": vresult.audio_score,
                                "visual_score": vresult.visual_score,
                                "combined_score": vresult.combined_score,
                                "gemini_detected_sport": vresult.gemini_detected_sport,
                            },
                            {
                                "source_platform": candidate.source_platform,
                                "source_url": candidate.source_url,
                                "discovered_at": candidate.discovered_at,
                                "candidate_metadata": candidate.candidate_metadata,
                            },
                            {
                                "id": str(match.id),
                                "name": match.name,
                            },
                            rights_holder,
                        ),
                        timeout=settings.dmca_generation_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    logger.error("DMCA generation timed out")
                    return None

                # Open takedown case
                case_id = await self.tracker.open_case(
                    session,
                    str(vresult.id),
                    str(candidate.id),
                    str(match.id),
                    draft_notice,
                )

                # Emit TakedownDrafted event to takedowns stream
                await self._emit_takedown_drafted(
                    {
                        "case_id": case_id,
                        "platform": draft_notice.platform,
                        "match_id": str(match.id),
                        "candidate_id": str(candidate.id),
                        "subject": draft_notice.subject,
                    }
                )

                await session.commit()
                logger.info(f"DMCA notice drafted for case {case_id}")
                return case_id

        except Exception as e:
            logger.error(f"Error processing DMCA event: {e}", exc_info=True)
            return None

    async def _emit_takedown_drafted(self, event_data: dict) -> None:
        """Emit a TakedownDrafted event to the takedowns stream."""
        stream_key = settings.redis_takedowns_stream
        try:
            await self.redis.xadd(
                stream_key,
                {"data": json.dumps(event_data)},
            )
            logger.debug(f"Emitted TakedownDrafted event to {stream_key}")
        except Exception as e:
            logger.error(f"Failed to emit takedown event: {e}")

    async def run(self, consumer_name: str = "dmca_worker") -> None:
        """
        Run the DMCA consumer loop.

        Reads from piratehunt:pirates stream and generates DMCA notices.
        """
        stream_key = "piratehunt:pirates"
        last_id = "0"

        logger.info(f"Starting DMCA worker on stream {stream_key}")

        while True:
            try:
                # Read from stream (block for 1 second)
                messages = await self.redis.xread(
                    {stream_key: last_id}, block=1000
                )

                if not messages:
                    continue

                for _, stream_messages in messages:
                    for msg_id, msg_data in stream_messages:
                        try:
                            if b"data" in msg_data:
                                event_data = json.loads(
                                    msg_data[b"data"].decode()
                                )
                                case_id = await self.process_event(event_data)
                                if case_id:
                                    logger.info(
                                        f"Processed pirate event, case: {case_id}"
                                    )
                            last_id = msg_id
                        except Exception as e:
                            logger.error(
                                f"Error processing stream message: {e}",
                                exc_info=True,
                            )

            except asyncio.CancelledError:
                logger.info("DMCA worker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in DMCA worker loop: {e}", exc_info=True)
                await asyncio.sleep(5)


async def run_dmca_worker() -> None:
    """Entry point for running the DMCA worker."""
    # Create async engine and session
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Create Redis client
    redis_client = await redis.from_url(settings.redis_url)

    try:
        worker = DMCAWorker(redis_client, async_session)
        await worker.run()
    finally:
        await redis_client.aclose()
        await engine.dispose()
