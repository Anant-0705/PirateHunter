"""Tests for DMCA takedown tracking."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from piratehunt.dmca.tracker import TakedownTracker
from piratehunt.dmca.types import DraftNotice, InvalidTransitionError, TakedownStatus


@pytest.fixture
def draft_notice():
    """Create a test draft notice."""
    return DraftNotice(
        platform="youtube",
        recipient_email_or_form_url="copyright@youtube.com",
        subject="DMCA Takedown Notice",
        body="Notice body content",
        language="en",
        gemini_polish_applied=False,
        fingerprint_match_scores={"audio": 0.97, "visual": 0.94},
    )


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


class TestTakedownTracker:
    """Test takedown case tracking."""

    @pytest.mark.asyncio
    async def test_open_case_creates_case_and_event(
        self, mock_session, draft_notice
    ):
        """Test that open_case creates TakedownCase and initial TakedownEvent."""
        tracker = TakedownTracker()

        case_id = await tracker.open_case(
            mock_session,
            "vresult-123",
            "candidate-456",
            "match-789",
            draft_notice,
        )

        assert case_id
        # Verify session.add was called at least twice (case and event)
        assert mock_session.add.call_count >= 2
        assert mock_session.flush.called

    @pytest.mark.asyncio
    async def test_open_case_sets_drafted_status(self, mock_session, draft_notice):
        """Test that opened case has drafted status."""
        from sqlalchemy.ext.asyncio import AsyncSession

        # Create a mock session with proper behavior for the test
        session = AsyncMock(spec=AsyncSession)
        session.flush = AsyncMock()
        session.add = MagicMock()

        tracker = TakedownTracker()
        await tracker.open_case(
            session,
            "vresult-123",
            "candidate-456",
            "match-789",
            draft_notice,
        )

        # Get the added TakedownCase from the mock calls
        calls = session.add.call_args_list
        assert len(calls) >= 1

        # The first call should be the TakedownCase
        case_call = calls[0]
        added_case = case_call[0][0]
        assert hasattr(added_case, "status")
        assert added_case.status == TakedownStatus.drafted

    @pytest.mark.asyncio
    async def test_valid_status_transitions(self, mock_session):
        """Test valid status transitions."""
        from piratehunt.db.models import TakedownCase

        tracker = TakedownTracker()

        # Valid transitions: drafted -> pending_review -> submitted -> acknowledged -> taken_down
        valid_path = [
            TakedownStatus.drafted,
            TakedownStatus.pending_review,
            TakedownStatus.submitted,
            TakedownStatus.acknowledged,
            TakedownStatus.taken_down,
        ]

        # Create a mock case
        mock_case = MagicMock(spec=TakedownCase)
        mock_case.id = uuid.uuid4()
        mock_case.status = TakedownStatus.drafted
        mock_case.notes = ""

        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(
            return_value=mock_case
        )
        mock_session.add = MagicMock()

        # Transition through valid path
        for i in range(len(valid_path) - 1):
            current_status = valid_path[i]
            next_status = valid_path[i + 1]
            mock_case.status = current_status

            await tracker.update_status(
                mock_session,
                str(mock_case.id),
                next_status,
                actor="system",
            )

            # Verify event was added
            assert mock_session.add.called

    @pytest.mark.asyncio
    async def test_invalid_status_transition_raises_error(self, mock_session):
        """Test that invalid transitions raise InvalidTransitionError."""
        from piratehunt.db.models import TakedownCase

        tracker = TakedownTracker()

        # Create a mock case in taken_down state
        mock_case = MagicMock(spec=TakedownCase)
        mock_case.id = uuid.uuid4()
        mock_case.status = TakedownStatus.taken_down  # Terminal state

        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(
            return_value=mock_case
        )

        # Try to transition from terminal state
        with pytest.raises(InvalidTransitionError):
            await tracker.update_status(
                mock_session,
                str(mock_case.id),
                TakedownStatus.pending_review,  # Invalid from taken_down
                actor="system",
            )

    @pytest.mark.asyncio
    async def test_case_not_found_raises_error(self, mock_session):
        """Test that updating non-existent case raises error."""
        tracker = TakedownTracker()

        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(
            return_value=None
        )

        with pytest.raises(ValueError, match="not found"):
            await tracker.update_status(
                mock_session,
                str(uuid.uuid4()),
                TakedownStatus.pending_review,
                actor="system",
            )

    @pytest.mark.asyncio
    async def test_rejection_terminal_transition(self, mock_session):
        """Test rejection as terminal transition from any state."""
        from piratehunt.db.models import TakedownCase

        tracker = TakedownTracker()

        for source_status in [
            TakedownStatus.drafted,
            TakedownStatus.pending_review,
            TakedownStatus.submitted,
        ]:
            mock_case = MagicMock(spec=TakedownCase)
            mock_case.id = uuid.uuid4()
            mock_case.status = source_status
            mock_case.notes = ""

            mock_session.execute = AsyncMock()
            mock_session.execute.return_value.scalar_one_or_none = MagicMock(
                return_value=mock_case
            )
            mock_session.add = MagicMock()

            # Should be able to reject from any state
            await tracker.update_status(
                mock_session,
                str(mock_case.id),
                TakedownStatus.rejected,
                actor="system",
            )

            assert mock_session.add.called

    @pytest.mark.asyncio
    async def test_update_status_records_transition_event(self, mock_session):
        """Test that status transitions are recorded as events."""
        from piratehunt.db.models import TakedownCase

        tracker = TakedownTracker()

        mock_case = MagicMock(spec=TakedownCase)
        mock_case.id = uuid.uuid4()
        mock_case.status = TakedownStatus.drafted
        mock_case.notes = ""

        mock_session.execute = AsyncMock()
        mock_session.execute.return_value.scalar_one_or_none = MagicMock(
            return_value=mock_case
        )
        mock_session.add = MagicMock()

        await tracker.update_status(
            mock_session,
            str(mock_case.id),
            TakedownStatus.pending_review,
            actor="user:123",
            notes="Reviewed and approved",
        )

        # Verify event creation
        calls = mock_session.add.call_args_list
        event_call = calls[-1]  # Last call should be the event
        added_event = event_call[0][0]

        assert hasattr(added_event, "from_status")
        assert hasattr(added_event, "to_status")
        assert hasattr(added_event, "actor")
