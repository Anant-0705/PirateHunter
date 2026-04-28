from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from piratehunt.agents.types import CandidateStream
from piratehunt.api.app import app
from piratehunt.db.engine import async_session_maker, engine
from piratehunt.db.models import Base, CandidateStatus
from piratehunt.db.repository import (
    create_match,
    insert_candidate_stream,
    list_candidates,
    update_candidate_status,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_discovery_api_candidate_listing_and_status_transition():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        match = await create_match(session, "API Discovery", "https://example.com/demo.mp4")

    with TestClient(app) as client:
        discover_response = client.post(
            f"/matches/{match.id}/discover",
            json={
                "keywords": ["ipl"],
                "languages": ["en", "hi"],
                "region_hints": ["IN"],
            },
        )

    assert discover_response.status_code == 202
    assert "discovery_run_id" in discover_response.json()

    async with async_session_maker() as session:
        inserted = await insert_candidate_stream(
            session,
            CandidateStream(
                match_id=match.id,
                source_platform="telegram",
                source_url="https://t.me/fake_ipl_live_hd_2026",
                discovered_by_agent="telegram",
                metadata={"is_pirate": True},
                confidence_hint=0.88,
            ),
        )
        assert inserted is not None
        updated = await update_candidate_status(
            session,
            inserted.id,
            CandidateStatus.queued_for_verification,
        )
        assert updated is not None

        candidates = await list_candidates(
            session,
            match.id,
            status=CandidateStatus.queued_for_verification,
            platform="telegram",
        )

    assert len(candidates) == 1
    assert candidates[0].source_url == "https://t.me/fake_ipl_live_hd_2026"
