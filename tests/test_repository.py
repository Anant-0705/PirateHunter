from __future__ import annotations

import pytest
from sqlalchemy import text

from piratehunt.db.engine import async_session_maker, engine
from piratehunt.db.models import Base, MatchStatus
from piratehunt.db.repository import (
    bulk_insert_audio_fingerprints,
    bulk_insert_visual_fingerprints,
    create_match,
    get_match,
    phash_to_vector,
    search_visual_fingerprints,
    update_match_status,
)
from piratehunt.fingerprint.types import AudioFingerprint, VisualFingerprint

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_repository_round_trip_and_vector_search():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        match = await create_match(session, "Demo", "https://example.com/demo.mp4")
        await update_match_status(session, match.id, MatchStatus.ingesting)
        await bulk_insert_audio_fingerprints(
            session,
            match.id,
            [
                AudioFingerprint(
                    fingerprint_hash="chromaprint-a",
                    duration_s=5.0,
                    source_id=str(match.id),
                    chunk_index=0,
                    start_seconds=0.0,
                )
            ],
        )
        await bulk_insert_visual_fingerprints(
            session,
            match.id,
            [
                VisualFingerprint(
                    phash="0000000000000000",
                    dhash="0000000000000000",
                    frame_index=0,
                    source_id=str(match.id),
                    timestamp_seconds=0.0,
                ),
                VisualFingerprint(
                    phash="ffffffffffffffff",
                    dhash="ffffffffffffffff",
                    frame_index=1,
                    source_id=str(match.id),
                    timestamp_seconds=1.0,
                ),
            ],
        )

        fetched = await get_match(session, match.id)
        assert fetched is not None
        assert fetched.name == "Demo"

        hits = await search_visual_fingerprints(
            session,
            phash_to_vector("0000000000000000"),
            top_k=1,
        )
        assert hits[0][0].frame_index == 0
        assert hits[0][1] == 0.0
