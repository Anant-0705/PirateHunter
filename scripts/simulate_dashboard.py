import asyncio
import uuid
import datetime
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from piratehunt.config import settings
from piratehunt.db.engine import _async_database_url
from piratehunt.db.models import Match, CandidateStream, VerificationResult, CandidateStatus, VerificationVerdict, MatchStatus
from piratehunt.api.realtime.types import CandidateDiscovered, PirateConfirmed, GeoLocation

async def main():
    # Setup DB and Redis connections
    engine = create_async_engine(_async_database_url(settings.database_url))
    SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis = Redis.from_url(settings.redis_url)
    
    # This is the UUID your dashboard is currently watching
    match_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    
    async with SessionLocal() as db:
        # Create match if not exists
        match = await db.get(Match, match_id)
        if not match:
            match = Match(id=match_id, name="Demo Cricket Match - India vs Australia", source_url="mock://stream", status=MatchStatus.ready)
            db.add(match)
            await db.commit()

        # 1. Simulate finding a pirate candidate
        candidate_id = uuid.uuid4()
        candidate = CandidateStream(
            id=candidate_id,
            match_id=match_id,
            source_platform="youtube",
            source_url=f"https://youtube.com/watch?v={str(candidate_id)[:8]}",
            discovered_at=datetime.datetime.utcnow(),
            discovered_by_agent="demo_agent",
            candidate_metadata={"live": True, "viewers": 15000},
            confidence_hint=0.92,
            status=CandidateStatus.verified_pirate,
            verified_at=datetime.datetime.utcnow(),
        )
        db.add(candidate)
        
        # 2. Simulate the AI Verification Process completing
        verification = VerificationResult(
            candidate_id=candidate_id,
            match_id=match_id,
            audio_score=0.98,
            visual_score=0.95,
            combined_score=0.96,
            gemini_is_sports=True,
            gemini_detected_sport="cricket",
            verdict=VerificationVerdict.pirate,
            latency_ms=1200
        )
        db.add(verification)
        await db.commit()

    # 3. Push real-time events to Redis so the Dashboard updates instantly via WebSockets!
    loc = GeoLocation(lat=28.6139, lng=77.2090, country="IN", country_name="India", city="New Delhi")
    
    event1 = CandidateDiscovered(
        match_id=str(match_id),
        candidate_id=str(candidate_id),
        platform="youtube",
        url=candidate.source_url,
        location=loc,
        confidence_hint=0.92
    )
    
    event2 = PirateConfirmed(
        match_id=str(match_id),
        candidate_id=str(candidate_id),
        verification_result_id=str(verification.id),
        platform="youtube",
        url=candidate.source_url,
        location=loc,
        audio_score=0.98,
        visual_score=0.95,
        combined_score=0.96,
        gemini_verdict="Pirate Cricket Stream",
        detection_latency_ms=1200.0
    )

    print("📡 Sending CandidateDiscovered Event...")
    await redis.publish(f"dashboard:events:{match_id}", event1.model_dump_json())
    
    await asyncio.sleep(1.5) # Slight delay to see the UI react in two steps
    
    print("🚨 Sending PirateConfirmed Event...")
    await redis.publish(f"dashboard:events:{match_id}", event2.model_dump_json())

    print(f"\n✅ Success! A pirate stream was added to the DB and broadcasted via WebSockets.")
    print(f"Check your dashboard at http://localhost:3000 to see the new data and globe markers!")
    
if __name__ == "__main__":
    asyncio.run(main())
