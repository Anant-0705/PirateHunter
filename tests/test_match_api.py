from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from piratehunt.api.app import app
from piratehunt.db.engine import async_session_maker, engine
from piratehunt.db.models import Base, MatchStatus
from piratehunt.db.repository import (
    bulk_insert_audio_fingerprints,
    bulk_insert_visual_fingerprints,
    create_match,
    update_match_status,
)
from piratehunt.fingerprint.types import AudioFingerprint, VisualFingerprint

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_match_check_scores_high_for_expected_match(monkeypatch):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        match = await create_match(session, "API Demo", "https://example.com/demo.mp4")
        audio = AudioFingerprint(
            fingerprint_hash="stable-chromaprint",
            duration_s=5.0,
            source_id=str(match.id),
            match_id=match.id,
            chunk_index=0,
            start_seconds=0.0,
        )
        visual = VisualFingerprint(
            phash="0000000000000000",
            dhash="0000000000000000",
            frame_index=0,
            source_id=str(match.id),
            match_id=match.id,
            timestamp_seconds=0.0,
        )
        await bulk_insert_audio_fingerprints(session, match.id, [audio])
        await bulk_insert_visual_fingerprints(session, match.id, [visual])
        await update_match_status(session, match.id, MatchStatus.ready)

    async def fake_fingerprint_sample(_source):
        return (
            [
                AudioFingerprint(
                    fingerprint_hash="stable-chromaprint", duration_s=5.0, source_id="q"
                )
            ],
            [
                VisualFingerprint(
                    phash="0000000000000000", dhash="0" * 16, frame_index=0, source_id="q"
                )
            ],
        )

    monkeypatch.setattr(
        "piratehunt.api.routers.matches._fingerprint_sample", fake_fingerprint_sample
    )

    with TestClient(app) as client:
        response = client.post(
            "/match/check", json={"source_url": "https://example.com/candidate.mp4"}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["match_id"] == str(match.id)
    assert payload[0]["combined_score"] > 0.8
