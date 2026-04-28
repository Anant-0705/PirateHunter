from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.api.dependencies import get_db
from piratehunt.db.models import TakedownCase, TakedownEvent
from piratehunt.dmca.tracker import TakedownTracker
from piratehunt.dmca.types import (
    InvalidTransitionError,
    TakedownCaseInfo,
    TakedownEventInfo,
    TakedownStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/takedowns", tags=["dmca"])


class TransitionRequest(BaseModel):
    """Request body for status transition."""

    new_status: TakedownStatus
    notes: Optional[str] = None


class RegenerateRequest(BaseModel):
    """Request body for regenerating a notice."""

    notes: Optional[str] = None


@router.get("/", response_model=dict)
async def list_takedowns(
    status: Optional[TakedownStatus] = Query(None, description="Filter by status"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    match_id: Optional[str] = Query(None, description="Filter by match ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List takedown cases with optional filtering and pagination."""
    query = select(TakedownCase)

    if status:
        query = query.where(TakedownCase.status == status)
    if platform:
        query = query.where(TakedownCase.platform == platform)
    if match_id:
        query = query.where(TakedownCase.match_id == match_id)

    result = await db.execute(
        query.offset(skip).limit(limit).order_by(TakedownCase.drafted_at.desc())
    )
    cases = result.scalars().all()

    return {
        "items": [_case_to_info(c, []) for c in cases],
        "total": len(cases),
        "skip": skip,
        "limit": limit,
    }


@router.get("/{case_id}", response_model=TakedownCaseInfo)
async def get_takedown(case_id: str, db: AsyncSession = Depends(get_db)) -> TakedownCaseInfo:
    """Get a takedown case with full event history."""
    result = await db.execute(
        select(TakedownCase).where(TakedownCase.id == case_id)
    )
    case = result.scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    return _case_to_info(case, case.events)


@router.post("/{case_id}/transition", response_model=TakedownCaseInfo)
async def transition_status(
    case_id: str,
    request: TransitionRequest,
    db: AsyncSession = Depends(get_db),
) -> TakedownCaseInfo:
    """Transition a case to a new status."""
    result = await db.execute(
        select(TakedownCase).where(TakedownCase.id == case_id)
    )
    case = result.scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    tracker = TakedownTracker()
    try:
        await tracker.update_status(
            db,
            case_id,
            request.new_status,
            actor="user:api",
            notes=request.notes,
        )
        await db.commit()

        # Fetch updated case
        result = await db.execute(
            select(TakedownCase).where(TakedownCase.id == case_id)
        )
        updated_case = result.scalar_one()
        return _case_to_info(updated_case, updated_case.events)

    except InvalidTransitionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(f"Error transitioning case: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to transition case",
        ) from e


@router.post("/{case_id}/regenerate", response_model=TakedownCaseInfo)
async def regenerate_notice(
    case_id: str,
    request: RegenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> TakedownCaseInfo:
    """Regenerate a DMCA notice (e.g., after rights-holder details updated)."""
    result = await db.execute(
        select(TakedownCase).where(TakedownCase.id == case_id)
    )
    case = result.scalar_one_or_none()

    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # For Phase 5, regeneration is a manual workflow placeholder
    # In production, would re-run DMCAGenerator and update draft fields
    logger.info(f"Regenerating notice for case {case_id}")

    return _case_to_info(case, case.events)


@router.get("/matches/{match_id}/takedowns", response_model=list[TakedownCaseInfo])
async def get_match_takedowns(
    match_id: str, db: AsyncSession = Depends(get_db)
) -> list[TakedownCaseInfo]:
    """Get all takedown cases for a match."""
    result = await db.execute(
        select(TakedownCase)
        .where(TakedownCase.match_id == match_id)
        .order_by(TakedownCase.drafted_at.desc())
    )
    cases = result.scalars().all()

    return [_case_to_info(c, c.events) for c in cases]


def _case_to_info(case: TakedownCase, events: list[TakedownEvent]) -> TakedownCaseInfo:
    """Convert TakedownCase model to info DTO."""
    return TakedownCaseInfo(
        id=str(case.id),
        verification_result_id=str(case.verification_result_id),
        candidate_id=str(case.candidate_id),
        match_id=str(case.match_id),
        platform=case.platform,
        status=case.status,
        draft_subject=case.draft_subject,
        draft_body=case.draft_body,
        draft_language=case.draft_language,
        recipient=case.recipient,
        gemini_polish_applied=case.gemini_polish_applied,
        drafted_at=case.drafted_at,
        last_status_at=case.last_status_at,
        submitted_at=case.submitted_at,
        resolved_at=case.resolved_at,
        notes=case.notes,
        events=[
            TakedownEventInfo(
                id=str(e.id),
                case_id=str(e.case_id),
                from_status=e.from_status,
                to_status=e.to_status,
                actor=e.actor,
                payload=e.payload,
                created_at=e.created_at,
            )
            for e in events
        ],
    )
