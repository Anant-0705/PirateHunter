"""Dashboard aggregation endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.api.dependencies import get_db
from piratehunt.api.realtime.types import (
    DashboardSummary,
    PirateEntry,
    TakedownFunnelData,
    TimelineEvent,
)
from piratehunt.config import settings
from piratehunt.db.models import (
    CandidateStream,
    Match,
    TakedownCase,
    TakedownStatus,
    VerificationResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# CPM (Cost Per Mille) for revenue calculations in INR
DEFAULT_CPM_INR = 150

# Platform viewer count priors (best-effort estimates)
PLATFORM_VIEWERS = {
    "youtube": 2000,  # 2000-5000 viewers typical
    "telegram": 800,  # 500-5000 viewers
    "discord": 300,  # 50-500 viewers
    "reddit": 400,  # Varies widely
    "twitter": 500,  # Varies
    "twitch": 1500,
    "kick": 1000,
    "unknown": 500,
}


@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    match_id: str = Query(..., description="Match UUID"),
    db: AsyncSession = Depends(get_db),
) -> DashboardSummary:
    """Get summary statistics for a match dashboard."""
    # Count verified pirates (pirate_confirmed)
    pirate_count = await db.scalar(
        select(func.count(VerificationResult.id)).where(
            VerificationResult.match_id == match_id,
            VerificationResult.verdict == "pirate",
        )
    )
    pirate_count = pirate_count or 0

    # Count DMCA cases
    draft_count = await db.scalar(
        select(func.count(TakedownCase.id)).where(TakedownCase.match_id == match_id)
    )
    draft_count = draft_count or 0

    # Count submitted
    submitted_count = await db.scalar(
        select(func.count(TakedownCase.id)).where(
            TakedownCase.match_id == match_id,
            TakedownCase.status.in_([TakedownStatus.submitted, TakedownStatus.acknowledged, TakedownStatus.taken_down]),
        )
    )
    submitted_count = submitted_count or 0

    # Count taken down
    taken_down_count = await db.scalar(
        select(func.count(TakedownCase.id)).where(
            TakedownCase.match_id == match_id,
            TakedownCase.status == TakedownStatus.taken_down,
        )
    )
    taken_down_count = taken_down_count or 0

    # Calculate average detection latency
    from sqlalchemy import cast, Float
    from sqlalchemy.dialects.postgresql import INTERVAL

    avg_latency_ms = await db.scalar(
        select(func.avg(
            cast(
                func.extract("epoch", VerificationResult.verified_at - CandidateStream.discovered_at) * 1000,
                Float
            )
        )).select_from(VerificationResult).join(
            CandidateStream, VerificationResult.candidate_id == CandidateStream.id
        ).where(
            VerificationResult.match_id == match_id,
            VerificationResult.verified_at.isnot(None),
            CandidateStream.discovered_at.isnot(None),
        )
    )
    avg_latency_ms = avg_latency_ms or 0

    # Get top platforms
    top_platforms_result = await db.execute(
        select(
            CandidateStream.source_platform,
            func.count(CandidateStream.id).label("count"),
        )
        .join(VerificationResult, VerificationResult.candidate_id == CandidateStream.id)
        .where(
            VerificationResult.match_id == match_id,
            VerificationResult.verdict == "pirate",
        )
        .group_by(CandidateStream.source_platform)
        .order_by(func.count(CandidateStream.id).desc())
        .limit(5)
    )
    top_platforms = [
        {"platform": row[0], "count": row[1]} for row in top_platforms_result
    ]

    # Estimate revenue loss
    # For demo: assume avg match duration 3 hours (typical sports broadcast)
    match_duration_seconds = 3 * 3600
    est_revenue_loss = 0
    for platform, viewers in PLATFORM_VIEWERS.items():
        platform_pirates = next((p for p in top_platforms if p["platform"] == platform), None)
        if platform_pirates:
            count = platform_pirates["count"]
            # Revenue loss = viewers × CPM × hours
            loss = viewers * count * DEFAULT_CPM_INR * match_duration_seconds / 3600 / 1000
            est_revenue_loss += loss

    return DashboardSummary(
        match_id=match_id,
        active_pirates=pirate_count - submitted_count,  # Not yet submitted
        total_detected=pirate_count,
        total_drafted=draft_count,
        total_submitted=submitted_count,
        total_taken_down=taken_down_count,
        est_revenue_loss_inr=est_revenue_loss,
        avg_detection_latency_ms=avg_latency_ms,
        top_platforms=top_platforms,
    )


@router.get("/timeline", response_model=list[TimelineEvent])
async def get_timeline(
    match_id: str = Query(..., description="Match UUID"),
    window: int = Query(60, ge=1, le=1440, description="Time window in minutes"),
    db: AsyncSession = Depends(get_db),
) -> list[TimelineEvent]:
    """Get time-bucketed event counts for the last N minutes."""
    now = datetime.utcnow()
    start_time = now - timedelta(minutes=window)

    # Get verification verdicts (pirates) per minute
    pirate_events = await db.execute(
        select(
            func.date_trunc("minute", VerificationResult.verified_at).label("minute"),
            func.count(VerificationResult.id).label("count"),
        )
        .where(
            VerificationResult.match_id == match_id,
            VerificationResult.verdict == "pirate",
            VerificationResult.verified_at >= start_time,
        )
        .group_by("minute")
        .order_by("minute")
    )

    # Get takedown transitions per minute
    takedown_events = await db.execute(
        select(
            func.date_trunc("minute", TakedownCase.drafted_at).label("minute"),
            func.count(TakedownCase.id).label("count"),
        )
        .where(
            TakedownCase.match_id == match_id,
            TakedownCase.drafted_at >= start_time,
        )
        .group_by("minute")
        .order_by("minute")
    )

    pirate_dict = {row[0]: row[1] for row in pirate_events}
    takedown_dict = {row[0]: row[1] for row in takedown_events}

    # Generate timeline with both metrics
    timeline = []
    current = start_time
    while current <= now:
        minute_bucket = func.date_trunc("minute", current)
        timeline.append(
            TimelineEvent(
                timestamp=current,
                detections=pirate_dict.get(current, 0),
                takedowns=takedown_dict.get(current, 0),
            )
        )
        current += timedelta(minutes=1)

    return timeline


@router.get("/pirates/active", response_model=list[PirateEntry])
async def get_active_pirates(
    match_id: str = Query(..., description="Match UUID"),
    db: AsyncSession = Depends(get_db),
) -> list[PirateEntry]:
    """Get currently active pirate streams not yet taken down."""
    from piratehunt.api.realtime.geolocation import lookup_location

    # Get verified pirates not yet taken down
    candidates = await db.execute(
        select(CandidateStream, VerificationResult)
        .join(VerificationResult, VerificationResult.candidate_id == CandidateStream.id)
        .outerjoin(TakedownCase, TakedownCase.candidate_id == CandidateStream.id)
        .where(
            VerificationResult.match_id == match_id,
            VerificationResult.verdict == "pirate",
            (TakedownCase.id.is_(None) | (TakedownCase.status != TakedownStatus.taken_down)),
        )
    )

    pirates = []
    for candidate, vresult in candidates:
        location = lookup_location(candidate.source_url)
        
        # Determine status
        status = "active"
        if vresult.verdict == "pirate":
            # Check for takedown case
            takedown_result = await db.execute(
                select(TakedownCase).where(
                    TakedownCase.candidate_id == candidate.id
                )
            )
            takedown = takedown_result.scalar_one_or_none()
            if takedown:
                if takedown.status in [TakedownStatus.submitted, TakedownStatus.acknowledged]:
                    status = "submitted"
                elif takedown.status == TakedownStatus.drafted:
                    status = "draft"

        pirates.append(
            PirateEntry(
                candidate_id=str(candidate.id),
                platform=candidate.source_platform,
                url=candidate.source_url,
                confidence=vresult.combined_score if vresult else 0,
                location=location,
                discovered_at=candidate.discovered_at or datetime.utcnow(),
                last_seen=vresult.verified_at or datetime.utcnow(),
                status=status,
            )
        )

    return pirates


@router.get("/funnel", response_model=TakedownFunnelData)
async def get_takedown_funnel(
    match_id: str = Query(..., description="Match UUID"),
    db: AsyncSession = Depends(get_db),
) -> TakedownFunnelData:
    """Get takedown funnel data (detected → verified → drafted → submitted → taken down)."""
    # Detected (any candidate)
    detected = await db.scalar(
        select(func.count(CandidateStream.id)).where(
            CandidateStream.match_id == match_id
        )
    )
    detected = detected or 0

    # Verified (verified_pirate verdict)
    verified = await db.scalar(
        select(func.count(VerificationResult.id)).where(
            VerificationResult.match_id == match_id,
            VerificationResult.verdict == "pirate",
        )
    )
    verified = verified or 0

    # Drafted (takedown case created)
    drafted = await db.scalar(
        select(func.count(TakedownCase.id)).where(
            TakedownCase.match_id == match_id
        )
    )
    drafted = drafted or 0

    # Submitted (status != drafted)
    submitted = await db.scalar(
        select(func.count(TakedownCase.id)).where(
            TakedownCase.match_id == match_id,
            TakedownCase.status.in_([
                TakedownStatus.submitted,
                TakedownStatus.acknowledged,
                TakedownStatus.taken_down,
            ]),
        )
    )
    submitted = submitted or 0

    # Taken down
    taken_down = await db.scalar(
        select(func.count(TakedownCase.id)).where(
            TakedownCase.match_id == match_id,
            TakedownCase.status == TakedownStatus.taken_down,
        )
    )
    taken_down = taken_down or 0

    return TakedownFunnelData(
        detected=detected,
        verified=verified,
        drafted=drafted,
        submitted=submitted,
        taken_down=taken_down,
    )
