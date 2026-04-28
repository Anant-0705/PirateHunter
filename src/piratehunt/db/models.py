from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for PirateHunt database models."""


class MatchStatus(str, enum.Enum):
    """Lifecycle states for an ingested match/source."""

    pending = "pending"
    ingesting = "ingesting"
    ready = "ready"
    failed = "failed"


class CandidateStatus(str, enum.Enum):
    """Verification lifecycle for discovered candidate streams."""

    discovered = "discovered"
    queued_for_verification = "queued_for_verification"
    verifying = "verifying"
    verified_pirate = "verified_pirate"
    verified_clean = "verified_clean"
    verification_failed = "verification_failed"


class AgentRunStatus(str, enum.Enum):
    """Lifecycle states for discovery agent runs."""

    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class VerificationVerdict(str, enum.Enum):
    """Final verification verdict."""

    pirate = "pirate"
    clean = "clean"
    inconclusive = "inconclusive"


class TakedownStatus(str, enum.Enum):
    """Lifecycle states for DMCA takedown cases."""

    drafted = "drafted"
    pending_review = "pending_review"
    submitted = "submitted"
    acknowledged = "acknowledged"
    taken_down = "taken_down"
    expired = "expired"
    rejected = "rejected"


class Match(Base):
    """A video source that PirateHunt fingerprints and searches against."""

    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, name="match_status"),
        nullable=False,
        default=MatchStatus.pending,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    audio_fingerprints: Mapped[list[AudioFingerprint]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    visual_fingerprints: Mapped[list[VisualFingerprint]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    candidate_streams: Mapped[list[CandidateStream]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    agent_runs: Mapped[list[AgentRun]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    verification_results: Mapped[list[VerificationResult]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class AudioFingerprint(Base):
    """Persisted audio fingerprint chunk for a match."""

    __tablename__ = "audio_fingerprints"
    __table_args__ = (Index("ix_audio_fingerprints_match_chunk", "match_id", "chunk_index"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    chromaprint_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    fallback_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    match: Mapped[Match] = relationship(back_populates="audio_fingerprints")


class VisualFingerprint(Base):
    """Persisted visual fingerprint for a video keyframe."""

    __tablename__ = "visual_fingerprints"
    __table_args__ = (
        Index("ix_visual_fingerprints_match_frame", "match_id", "frame_index"),
        Index(
            "ix_visual_fingerprints_phash_vector_hnsw",
            "phash_vector",
            postgresql_using="hnsw",
            postgresql_ops={"phash_vector": "vector_l2_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    phash: Mapped[str] = mapped_column(String(16), nullable=False)
    dhash: Mapped[str] = mapped_column(String(16), nullable=False)
    phash_vector: Mapped[list[float]] = mapped_column(Vector(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    match: Mapped[Match] = relationship(back_populates="visual_fingerprints")


class CandidateStream(Base):
    """A stream discovered by one of the source discovery agents."""

    __tablename__ = "candidate_streams"
    __table_args__ = (
        UniqueConstraint("match_id", "source_url", name="uq_candidate_streams_match_source_url"),
        Index("ix_candidate_streams_source_url", "source_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    source_platform: Mapped[str] = mapped_column(String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    discovered_by_agent: Mapped[str] = mapped_column(String(128), nullable=False)
    candidate_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    confidence_hint: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, name="candidate_status"),
        nullable=False,
        default=CandidateStatus.discovered,
        index=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    match: Mapped[Match] = relationship(back_populates="candidate_streams")
    verification_result: Mapped[VerificationResult | None] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )


class AgentRun(Base):
    """Operational record of one discovery agent run."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus, name="agent_run_status"),
        nullable=False,
        default=AgentRunStatus.running,
        index=True,
    )
    candidates_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    match: Mapped[Match] = relationship(back_populates="agent_runs")


class VerificationResult(Base):
    """Stored result of verifying one discovered candidate stream."""

    __tablename__ = "verification_results"
    __table_args__ = (
        Index(
            "ix_verification_results_match_verdict_verified", "match_id", "verdict", "verified_at"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("candidate_streams.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    audio_score: Mapped[float] = mapped_column(Float, nullable=False)
    visual_score: Mapped[float] = mapped_column(Float, nullable=False)
    combined_score: Mapped[float] = mapped_column(Float, nullable=False)
    gemini_is_sports: Mapped[bool | None] = mapped_column(nullable=True)
    gemini_detected_sport: Mapped[str | None] = mapped_column(String(128), nullable=True)
    gemini_broadcaster_logos: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    gemini_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    verdict: Mapped[VerificationVerdict] = mapped_column(
        Enum(VerificationVerdict, name="verification_verdict"),
        nullable=False,
        index=True,
    )
    evidence_artifact_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    candidate: Mapped[CandidateStream] = relationship(back_populates="verification_result")
    match: Mapped[Match] = relationship(back_populates="verification_results")
    overrides: Mapped[list[VerificationOverride]] = relationship(
        back_populates="verification", cascade="all, delete-orphan"
    )


class VerificationOverride(Base):
    """Audit record for manual verification verdict overrides."""

    __tablename__ = "verification_overrides"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    verification_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("verification_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_verdict: Mapped[VerificationVerdict] = mapped_column(
        Enum(VerificationVerdict, name="verification_verdict"),
        nullable=False,
    )
    override_verdict: Mapped[VerificationVerdict] = mapped_column(
        Enum(VerificationVerdict, name="verification_verdict"),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    overridden_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    verification: Mapped[VerificationResult] = relationship(back_populates="overrides")


class RightsHolder(Base):
    """Copyright rights holder information for DMCA notices."""

    __tablename__ = "rights_holders"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_email: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    authorized_agent: Mapped[str] = mapped_column(String(255), nullable=False)
    default_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    signature_block: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    takedown_cases: Mapped[list[TakedownCase]] = relationship(
        back_populates="rights_holder", cascade="all, delete-orphan"
    )


class TakedownCase(Base):
    """DMCA takedown case tracking."""

    __tablename__ = "takedown_cases"
    __table_args__ = (
        Index("ix_takedown_cases_status_drafted", "status", "drafted_at"),
        Index("ix_takedown_cases_verification_result", "verification_result_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    verification_result_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("verification_results.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("candidate_streams.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    rights_holder_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rights_holders.id", ondelete="SET NULL"),
        nullable=True,
    )
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[TakedownStatus] = mapped_column(
        Enum(TakedownStatus, name="takedown_status"),
        nullable=False,
        default=TakedownStatus.drafted,
        index=True,
    )
    draft_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    draft_body: Mapped[str] = mapped_column(Text, nullable=False)
    draft_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    gemini_polish_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    drafted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_status_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    verification_result: Mapped[VerificationResult] = relationship()
    candidate: Mapped[CandidateStream] = relationship()
    match: Mapped[Match] = relationship()
    rights_holder: Mapped[RightsHolder | None] = relationship(back_populates="takedown_cases")
    events: Mapped[list[TakedownEvent]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class TakedownEvent(Base):
    """Audit trail for takedown case status transitions."""

    __tablename__ = "takedown_events"
    __table_args__ = (Index("ix_takedown_events_case_created", "case_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("takedown_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_status: Mapped[TakedownStatus | None] = mapped_column(
        Enum(TakedownStatus, name="takedown_status"),
        nullable=True,
    )
    to_status: Mapped[TakedownStatus] = mapped_column(
        Enum(TakedownStatus, name="takedown_status"),
        nullable=False,
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    case: Mapped[TakedownCase] = relationship(back_populates="events")
