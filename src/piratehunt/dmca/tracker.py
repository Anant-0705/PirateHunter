from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.db.models import TakedownCase, TakedownEvent
from piratehunt.dmca.types import (
    VALID_TRANSITIONS,
    DraftNotice,
    InvalidTransitionError,
    TakedownStatus,
)

logger = logging.getLogger(__name__)


class TakedownTracker:
    """Track and manage DMCA takedown case lifecycle."""

    async def open_case(
        self,
        session: AsyncSession,
        verification_result_id: str,
        candidate_id: str,
        match_id: str,
        draft_notice: DraftNotice,
    ) -> str:
        """
        Create a new takedown case in drafted state.

        Args:
            session: SQLAlchemy async session
            verification_result_id: UUID of verification result
            candidate_id: UUID of candidate stream
            match_id: UUID of original match
            draft_notice: Generated draft notice

        Returns:
            Case ID (UUID)
        """
        case_id = str(uuid.uuid4())

        case = TakedownCase(
            id=uuid.UUID(case_id),
            verification_result_id=uuid.UUID(verification_result_id),
            candidate_id=uuid.UUID(candidate_id),
            match_id=uuid.UUID(match_id),
            platform=draft_notice.platform,
            status=TakedownStatus.drafted,
            draft_subject=draft_notice.subject,
            draft_body=draft_notice.body,
            draft_language=draft_notice.language,
            recipient=draft_notice.recipient_email_or_form_url,
            gemini_polish_applied=draft_notice.gemini_polish_applied,
            drafted_at=datetime.utcnow(),
            last_status_at=datetime.utcnow(),
            notes=f"Case opened. Fingerprint scores: {draft_notice.fingerprint_match_scores}",
        )

        session.add(case)

        # Create initial event record
        event = TakedownEvent(
            id=uuid.uuid4(),
            case_id=uuid.UUID(case_id),
            from_status=None,
            to_status=TakedownStatus.drafted,
            actor="system",
            payload={
                "platform": draft_notice.platform,
                "gemini_polish_applied": draft_notice.gemini_polish_applied,
            },
            created_at=datetime.utcnow(),
        )
        session.add(event)

        await session.flush()
        logger.info(f"Opened takedown case {case_id} for {draft_notice.platform}")

        return case_id

    async def update_status(
        self,
        session: AsyncSession,
        case_id: str,
        new_status: TakedownStatus,
        actor: str = "system",
        evidence_url: str | None = None,
        notes: str | None = None,
    ) -> None:
        """
        Transition a case to a new status with audit trail.

        Args:
            session: SQLAlchemy async session
            case_id: Case UUID
            new_status: Target status
            actor: Who made the transition (system or user:<id>)
            evidence_url: Optional evidence URL for acknowledgment/rejection
            notes: Optional notes on the transition

        Raises:
            InvalidTransitionError: If transition is not valid
        """
        from sqlalchemy import select

        # Fetch current case
        result = await session.execute(
            select(TakedownCase).where(TakedownCase.id == uuid.UUID(case_id))
        )
        case = result.scalar_one_or_none()

        if not case:
            raise ValueError(f"Case {case_id} not found")

        # Validate transition
        current_status = case.status
        valid_next = VALID_TRANSITIONS.get(current_status, [])

        if new_status not in valid_next:
            raise InvalidTransitionError(current_status, new_status)

        # Update case
        case.status = new_status
        case.last_status_at = datetime.utcnow()

        if new_status == TakedownStatus.submitted:
            case.submitted_at = datetime.utcnow()
        elif new_status in [TakedownStatus.taken_down, TakedownStatus.rejected, TakedownStatus.expired]:
            case.resolved_at = datetime.utcnow()

        if notes:
            case.notes = (case.notes or "") + f"\n[{datetime.utcnow().isoformat()}] {notes}"

        # Create event record
        event = TakedownEvent(
            id=uuid.uuid4(),
            case_id=uuid.UUID(case_id),
            from_status=current_status,
            to_status=new_status,
            actor=actor,
            payload={
                "evidence_url": evidence_url,
                "notes": notes,
            },
            created_at=datetime.utcnow(),
        )
        session.add(event)

        logger.info(
            f"Case {case_id} transitioned from {current_status} to {new_status} by {actor}"
        )
