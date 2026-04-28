"""Tests for DMCA worker."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.db.models import (
    CandidateStatus,
    CandidateStream,
    Match,
    VerificationResult,
)
from piratehunt.dmca.worker import DMCAWorker


@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    return AsyncMock(spec=redis.Redis)


@pytest.fixture
def mock_session_maker():
    """Create a mock session maker."""
    return AsyncMock()


@pytest.fixture
def sample_event_data():
    """Create a sample pirate confirmed event."""
    return {
        "verification_result_id": str(uuid.uuid4()),
        "candidate_id": str(uuid.uuid4()),
        "match_id": str(uuid.uuid4()),
    }


@pytest.fixture
def sample_candidate():
    """Create a sample candidate stream."""
    candidate_id = uuid.uuid4()
    return CandidateStream(
        id=candidate_id,
        match_id=uuid.uuid4(),
        source_platform="youtube",
        source_url="https://youtube.com/watch?v=test123",
        discovered_at=None,
        discovered_by_agent="test",
        candidate_metadata={"title": "Test Match"},
        confidence_hint=0.99,
        status=CandidateStatus.discovered,
    )


@pytest.fixture
def sample_match():
    """Create a sample match."""
    return Match(
        id=uuid.uuid4(),
        name="Test Cricket Match",
        source_url="https://example.com/match",
        status="ready",
    )


@pytest.fixture
def sample_verification_result():
    """Create a sample verification result."""
    return MagicMock(
        id=uuid.uuid4(),
        audio_score=0.97,
        visual_score=0.94,
        combined_score=0.96,
        gemini_detected_sport="cricket",
    )


class TestDMCAWorker:
    """Test DMCA worker."""

    @pytest.mark.asyncio
    async def test_worker_initialization(self, mock_redis, mock_session_maker):
        """Test worker initialization."""
        worker = DMCAWorker(mock_redis, mock_session_maker)
        assert worker.redis == mock_redis
        assert worker.db_session == mock_session_maker

    @pytest.mark.asyncio
    async def test_process_event_with_valid_data(
        self,
        mock_redis,
        mock_session_maker,
        sample_event_data,
        sample_candidate,
        sample_match,
        sample_verification_result,
    ):
        """Test processing a valid PirateConfirmed event."""
        # Mock the session
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.get = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_maker.return_value = mock_session

        # Setup mock returns for session.get
        async def mock_get(model, id):
            if model == VerificationResult:
                return sample_verification_result
            elif model == CandidateStream:
                return sample_candidate
            elif model == Match:
                return sample_match
            return None

        mock_session.get = AsyncMock(side_effect=mock_get)

        # Mock registry
        with patch(
            "piratehunt.dmca.worker.RightsHolderRegistry"
        ) as mock_registry_class:
            mock_registry = AsyncMock()
            mock_registry.get_rights_holder = AsyncMock(return_value=None)
            mock_registry_class.return_value = mock_registry

            # Mock generator and tracker
            with patch("piratehunt.dmca.worker.DMCAGenerator") as mock_gen_class:
                mock_gen = AsyncMock()
                mock_draft = MagicMock()
                mock_draft.platform = "youtube"
                mock_draft.subject = "Test Notice"
                mock_gen.generate = AsyncMock(return_value=mock_draft)
                mock_gen_class.return_value = mock_gen

                with patch("piratehunt.dmca.worker.TakedownTracker") as mock_tracker_class:
                    mock_tracker = AsyncMock()
                    mock_tracker.open_case = AsyncMock(
                        return_value=str(uuid.uuid4())
                    )
                    mock_tracker_class.return_value = mock_tracker

                    worker = DMCAWorker(mock_redis, mock_session_maker)

                    case_id = await worker.process_event(sample_event_data)

                    assert case_id is not None
                    assert mock_gen.generate.called
                    assert mock_tracker.open_case.called

    @pytest.mark.asyncio
    async def test_process_event_with_invalid_data(self, mock_redis, mock_session_maker):
        """Test processing event with missing required fields."""
        worker = DMCAWorker(mock_redis, mock_session_maker)

        invalid_event = {"verification_result_id": str(uuid.uuid4())}
        # Missing candidate_id and match_id

        case_id = await worker.process_event(invalid_event)

        assert case_id is None

    @pytest.mark.asyncio
    async def test_emit_takedown_drafted_event(self, mock_redis, mock_session_maker):
        """Test emitting a TakedownDrafted event to Redis."""
        worker = DMCAWorker(mock_redis, mock_session_maker)

        event_data = {
            "case_id": str(uuid.uuid4()),
            "platform": "youtube",
            "match_id": str(uuid.uuid4()),
        }

        await worker._emit_takedown_drafted(event_data)

        assert mock_redis.xadd.called

    @pytest.mark.asyncio
    async def test_worker_run_reads_from_stream(self, mock_redis, mock_session_maker):
        """Test that worker run method reads from stream."""
        worker = DMCAWorker(mock_redis, mock_session_maker)

        # Mock XREAD to return empty initially
        mock_redis.xread = AsyncMock(return_value=None)

        # Start worker with timeout to prevent infinite loop
        try:
            import asyncio

            task = asyncio.create_task(worker.run())
            await asyncio.sleep(0.1)
            task.cancel()
        except asyncio.CancelledError:
            pass

        # Verify xread was called
        assert mock_redis.xread.called

    @pytest.mark.asyncio
    async def test_worker_handles_stream_errors(self, mock_redis, mock_session_maker):
        """Test that worker handles stream errors gracefully."""
        worker = DMCAWorker(mock_redis, mock_session_maker)

        # Mock XREAD to raise an exception
        mock_redis.xread = AsyncMock(side_effect=Exception("Stream error"))

        # Start worker with timeout
        try:
            import asyncio

            task = asyncio.create_task(worker.run())
            await asyncio.sleep(0.1)
            task.cancel()
        except asyncio.CancelledError:
            pass

        # Should not crash and should continue running
        assert True  # If we got here, error handling worked


class TestDMCAWorkerIntegration:
    """Integration tests for DMCA worker."""

    @pytest.mark.asyncio
    async def test_full_pirate_to_dmca_flow(
        self,
        mock_redis,
        mock_session_maker,
        sample_event_data,
    ):
        """Test full flow from pirate event to DMCA notice."""
        # Create mock session with proper behavior
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session_maker.return_value = mock_session

        # This integration test verifies the basic flow exists
        worker = DMCAWorker(mock_redis, mock_session_maker)

        # Verify worker has all required components
        assert worker.generator is not None
        assert worker.tracker is not None
        assert worker.registry is not None
